#!/usr/bin/env python3
"""
ps5_windows_bridge.py — Windows-native PS5 DualSense -> Rock64 motor bridge.

Reads the PS5 controller via pygame (no WSL/evdev required), computes
differential drive motor speeds, and streams serial motor packets to the
Rock64 over a persistent SSH connection:

  ssh rock64@<ROCK64_IP> "stty -F /dev/ttyUSB0 115200 raw; cat > /dev/ttyUSB0"

Usage:
  python host_control/ps5_windows_bridge.py
  python host_control/ps5_windows_bridge.py --host 192.168.1.159 --port /dev/ttyUSB0
  python host_control/ps5_windows_bridge.py --list-joysticks

Requirements (install in Windows Python, not WSL):
  pip install pygame paramiko
"""

import argparse
import subprocess
import sys
import time
import threading
import json
import os

# Import platform utilities for cross-platform compatibility
from platform_utils import get_default_serial_port, get_ssh_key_path

# ---------------------------------------------------------------------------
# Axis / button layout for DualSense USB on Windows (pygame SDL mapping)
# ---------------------------------------------------------------------------
#  Axis 0  = Left  stick X  (left=-1, right=+1)
#  Axis 1  = Left  stick Y  (up=-1, down=+1)  ← INVERTED from intuition
#  Axis 2  = Right stick X  (left=-1, right=+1)
#  Axis 3  = Right stick Y  (up=-1, down=+1)
#  Axis 4  = L2 trigger     (-1 = released, +1 = fully pressed)
#  Axis 5  = R2 trigger     (-1 = released, +1 = fully pressed)
# ---------------------------------------------------------------------------

DEADZONE = 0.15       # ignore stick noise below this magnitude
LINEAR_SCALE = 200.0  # max motor speed for pure forward/back
ANGULAR_SCALE = 100.0 # max motor contribution from turning
MAX_SPEED = 180       # Reduced from 255 for safer operation
POLL_HZ = 20          # how often to send packets (Hz)

# Mode states
MODE_MANUAL = "MANUAL"
MODE_AGENT = "AGENT"
MODE_ESTOP = "E-STOP"

# Button indices for DualSense (may vary, check with --list-joysticks)
SHARE_BUTTON_INDEX = 8   # Share button for mode toggle
PS_BUTTON_INDEX = 0      # PS button for emergency stop
R3_BUTTON_INDEX = 11     # R3 (right stick press) for emergency stop

# Mode state file
MODE_STATE_FILE = os.path.join(os.path.dirname(__file__), "mode_state.json")


def clamp(value: float, limit: int = MAX_SPEED) -> int:
    return int(max(-limit, min(limit, value)))


def load_mode_state() -> str:
    """Load mode state from file, default to MANUAL."""
    try:
        if os.path.exists(MODE_STATE_FILE):
            with open(MODE_STATE_FILE, 'r') as f:
                state = json.load(f)
                return state.get('mode', MODE_MANUAL)
    except Exception:
        pass
    return MODE_MANUAL


def save_mode_state(mode: str) -> None:
    """Save mode state to file."""
    try:
        with open(MODE_STATE_FILE, 'w') as f:
            json.dump({'mode': mode}, f)
    except Exception:
        pass


def send_mode_to_agent(mode: str) -> None:
    """Send mode command to agent controller via IPC or file."""
    try:
        agent_mode_file = os.path.join(os.path.dirname(__file__), "agent_mode.txt")
        with open(agent_mode_file, 'w') as f:
            f.write(mode)
    except Exception:
        pass


def apply_deadzone(value: float, zone: float = DEADZONE) -> float:
    return 0.0 if abs(value) < zone else value


def motor_packet(motor_id: int, speed: int) -> bytes:
    """Format: <motor_id,direction,magnitude>\n  — same as arduino_serial_bridge"""
    if speed > 0:
        direction, magnitude = 'F', speed
    elif speed < 0:
        direction, magnitude = 'B', abs(speed)
    else:
        direction, magnitude = 'S', 0
    return f'<{motor_id},{direction},{magnitude}>\n'.encode()


def twist_to_wheel_speeds(linear_x: float, angular_z: float):
    """Differential drive: left = linear + angular, right = linear - angular"""
    left  = clamp(linear_x * LINEAR_SCALE + angular_z * ANGULAR_SCALE)
    right = clamp(linear_x * LINEAR_SCALE - angular_z * ANGULAR_SCALE)
    return left, right


def list_joysticks():
    import pygame
    pygame.init()
    pygame.joystick.init()
    count = pygame.joystick.get_count()
    if count == 0:
        print("No joysticks detected.")
    else:
        for i in range(count):
            js = pygame.joystick.Joystick(i)
            js.init()
            print(f"  [{i}] {js.get_name()}  axes={js.get_numaxes()}  buttons={js.get_numbuttons()}")
    pygame.quit()


def open_ssh_pipe(host: str, serial_port: str, baud: int, ssh_key: str,
                  dry_run: bool):
    """Open a persistent SSH pipe to the Rock64's serial port.

    Returns the ``subprocess.Popen`` whose ``stdin`` accepts raw motor
    packets, or ``None`` in dry-run mode. Exits the process on failure.
    """
    # Check if SSH key exists
    if not os.path.exists(ssh_key):
        print(f"ERROR: SSH key not found at {ssh_key}")
        print("Please ensure your SSH key exists or specify the correct path with --ssh-key")
        sys.exit(1)

    # First, check if the serial port exists
    check_cmd = [
        'ssh',
        '-i', ssh_key,
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'ConnectTimeout=10',
        f'rock64@{host}',
        f'test -c {serial_port} && echo "PORT_EXISTS" || echo "PORT_MISSING"',
    ]

    print(f"[bridge] Checking if {serial_port} exists on {host}...")
    try:
        result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=15)
        if "PORT_MISSING" in result.stdout:
            print(f"ERROR: Serial port {serial_port} does not exist on {host}")
            print(f"Available serial ports:")
            list_cmd = [
                'ssh',
                '-i', ssh_key,
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=10',
                f'rock64@{host}',
                'ls /dev/tty*',
            ]
            list_result = subprocess.run(list_cmd, capture_output=True, text=True, timeout=15)
            print(list_result.stdout)
            sys.exit(1)
        print(f"[bridge] Serial port {serial_port} exists.")
    except subprocess.TimeoutExpired:
        print(f"ERROR: SSH connection timed out while checking serial port.")
        print(f"Troubleshooting:")
        print(f"  1. Ensure Rock64 is reachable at {host}")
        print(f"  2. Check network connectivity: ping {host}")
        print(f"  3. Verify SSH key permissions and path: {ssh_key}")
        print(f"  4. Test SSH manually: ssh -i {ssh_key} rock64@{host}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: SSH connection failed: {e}")
        sys.exit(1)

    ssh_cmd = [
        'ssh',
        '-i', ssh_key,
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'ServerAliveInterval=5',
        '-o', 'ServerAliveCountMax=3',
        '-o', 'ConnectTimeout=10',
        f'rock64@{host}',
        f'stty -F {serial_port} {baud} raw -echo; cat > {serial_port}',
    ]

    if dry_run:
        print("[DRY-RUN] Would open SSH pipe:")
        print(" ", " ".join(ssh_cmd))
        return None

    print(f"[bridge] Connecting to {host} -> {serial_port} at {baud} baud...")
    try:
        ssh_proc = subprocess.Popen(
            ssh_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        print("ERROR: 'ssh' not found. Install OpenSSH or Git for Windows (which bundles ssh).")
        sys.exit(1)

    # Start a thread to read stderr and print any errors
    def read_stderr():
        for line in iter(ssh_proc.stderr.readline, b''):
            if line:
                print(f"[SSH STDERR] {line.decode().strip()}")

    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()

    # Give SSH a moment to connect
    time.sleep(2.0)
    if ssh_proc.poll() is not None:
        err = ssh_proc.stderr.read().decode()
        print(f"ERROR: SSH connection failed:\n{err}")
        print(f"Troubleshooting:")
        print(f"  1. Ensure Rock64 is reachable at {host}")
        print(f"  2. Check network connectivity: ping {host}")
        print(f"  3. Verify SSH key is correct: {ssh_key}")
        print(f"  4. Test SSH manually: ssh -i {ssh_key} rock64@{host}")
        sys.exit(1)
    print("[bridge] SSH connected.")
    return ssh_proc


def run_bridge(host: str, serial_port: str, baud: int, ssh_key: str,
               joystick_index: int, lefty_axis: int, rightx_axis: int,
               dry_run: bool):
    import pygame

    # ---- Load initial mode state -------------------------------------------
    current_mode = load_mode_state()
    print(f"[bridge] Initial mode: {current_mode}")

    # ---- Open SSH pipe to Rock64 serial port --------------------------------
    ssh_proc = open_ssh_pipe(host, serial_port, baud, ssh_key, dry_run)

    # ---- Init pygame joystick -----------------------------------------------
    pygame.init()
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    if count == 0:
        print("ERROR: No joysticks detected by pygame. Is the PS5 controller plugged in?")
        if ssh_proc:
            ssh_proc.terminate()
        sys.exit(1)

    if joystick_index >= count:
        print(f"ERROR: Joystick index {joystick_index} requested but only {count} found.")
        if ssh_proc:
            ssh_proc.terminate()
        sys.exit(1)

    js = pygame.joystick.Joystick(joystick_index)
    js.init()
    print(f"[bridge] Using joystick [{joystick_index}]: {js.get_name()}")
    print(f"         axes={js.get_numaxes()}  buttons={js.get_numbuttons()}")
    print()
    print("  Left stick Y  -> forward / back")
    print("  Right stick X -> turn left / right")
    print(f"  Share button -> Toggle mode (MANUAL <-> AGENT)")
    print(f"  PS button / R3 -> Emergency stop")
    print(f"  Current mode: {current_mode}")
    print("  Press Ctrl+C to stop (sends zero-speed packet first).")
    print()

    interval = 1.0 / POLL_HZ
    last_left, last_right = None, None
    last_share_state = False
    last_ps_state = False
    last_r3_state = False

    def send(left: int, right: int):
        pkt = motor_packet(1, right) + motor_packet(2, left)  # motor 1=right, 2=left
        if dry_run:
            print(f"  [dry] L={left:+4d} R={right:+4d}  ->  {pkt.decode().strip()}")
        else:
            try:
                ssh_proc.stdin.write(pkt)
                ssh_proc.stdin.flush()
            except BrokenPipeError:
                print("ERROR: SSH pipe closed. Is Rock64 still reachable?")
                raise

    try:
        while True:
            t_start = time.monotonic()

            # Drain pygame events (required to update axis values)
            pygame.event.pump()

            # Check button states for mode switching
            share_pressed = js.get_button(SHARE_BUTTON_INDEX)
            ps_pressed = js.get_button(PS_BUTTON_INDEX)
            r3_pressed = js.get_button(R3_BUTTON_INDEX)

            # Handle Share button (mode toggle)
            if share_pressed and not last_share_state:
                if current_mode == MODE_MANUAL:
                    current_mode = MODE_AGENT
                elif current_mode == MODE_AGENT:
                    current_mode = MODE_MANUAL
                save_mode_state(current_mode)
                send_mode_to_agent(current_mode)
                print(f"\n[bridge] Mode switched to: {current_mode}")
            last_share_state = share_pressed

            # Handle PS button or R3 (emergency stop)
            if (ps_pressed and not last_ps_state) or (r3_pressed and not last_r3_state):
                current_mode = MODE_ESTOP
                save_mode_state(current_mode)
                send_mode_to_agent(current_mode)
                print(f"\n[bridge] EMERGENCY STOP triggered!")
                send(0, 0)  # Stop motors immediately
            last_ps_state = ps_pressed
            last_r3_state = r3_pressed

            # Only send motor commands in MANUAL mode
            if current_mode == MODE_MANUAL:
                raw_linear  = -apply_deadzone(js.get_axis(lefty_axis))   # invert Y: up = forward
                raw_angular = -apply_deadzone(js.get_axis(rightx_axis))  # invert X: right stick right = turn right

                left_speed, right_speed = twist_to_wheel_speeds(raw_linear, raw_angular)

                # Always send every tick — Arduino has a 200ms heartbeat timeout that
                # releases motors if no packet arrives. Holding the stick must keep sending.
                send(left_speed, right_speed)

                # Print status line only when values change (avoids console spam)
                if (left_speed, right_speed) != (last_left, last_right):
                    last_left, last_right = left_speed, right_speed
                    l_bar = '#' * int(abs(left_speed)  / 25)
                    r_bar = '#' * int(abs(right_speed) / 25)
                    print(f"\r  L={left_speed:+4d} [{l_bar:<10}]   R={right_speed:+4d} [{r_bar:<10}]   Mode: {current_mode}  ", end='', flush=True)
            else:
                # In AGENT or E-STOP mode, don't send joystick commands
                if current_mode == MODE_AGENT:
                    print(f"\r  AGENT MODE active - waiting for agent commands...  ", end='', flush=True)
                elif current_mode == MODE_ESTOP:
                    print(f"\r  EMERGENCY STOP - motors stopped  ", end='', flush=True)

            elapsed = time.monotonic() - t_start
            time.sleep(max(0, interval - elapsed))

    except KeyboardInterrupt:
        print("\n\n[bridge] Stopping — sending zero speed...")
        try:
            send(0, 0)
        except Exception:
            pass
        # Reset mode to MANUAL on exit
        current_mode = MODE_MANUAL
        save_mode_state(current_mode)
        send_mode_to_agent(current_mode)

    finally:
        pygame.quit()
        if ssh_proc:
            try:
                ssh_proc.stdin.close()
            except Exception:
                pass
            ssh_proc.terminate()
        print("[bridge] Bye.")


def main():
    parser = argparse.ArgumentParser(
        description="Windows PS5 DualSense -> Rock64 motor bridge (no ROS2, no WSL)"
    )
    parser.add_argument('--host', default='192.168.1.159', help='Rock64 IP address')
    parser.add_argument('--port', default=get_default_serial_port(), help='Serial port on Rock64')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--ssh-key', default=get_ssh_key_path(),
                        help='Path to SSH private key for rock64 user')
    parser.add_argument('--joystick-index', type=int, default=0)
    parser.add_argument('--lefty-axis', type=int, default=1,
                        help='Axis index for left stick Y (forward/back)')
    parser.add_argument('--rightx-axis', type=int, default=2,
                        help='Axis index for right stick X (turn)')
    parser.add_argument('--list-joysticks', action='store_true',
                        help='List detected joysticks and exit')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print packets to console instead of sending over SSH')
    args = parser.parse_args()

    if args.list_joysticks:
        list_joysticks()
        return

    run_bridge(
        host=args.host,
        serial_port=args.port,
        baud=args.baud,
        ssh_key=args.ssh_key,
        joystick_index=args.joystick_index,
        lefty_axis=args.lefty_axis,
        rightx_axis=args.rightx_axis,
        dry_run=args.dry_run,
    )


if __name__ == '__main__':
    main()
