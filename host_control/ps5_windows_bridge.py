#!/usr/bin/env python3
"""
ps5_windows_bridge.py — Windows-native PS5 DualSense → Rock64 motor bridge.

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
MAX_SPEED = 255
POLL_HZ = 20          # how often to send packets (Hz)


def clamp(value: float, limit: int = MAX_SPEED) -> int:
    return int(max(-limit, min(limit, value)))


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


def run_bridge(host: str, serial_port: str, baud: int, ssh_key: str,
               joystick_index: int, lefty_axis: int, rightx_axis: int,
               dry_run: bool):
    import pygame

    # ---- Open SSH pipe to Rock64 serial port --------------------------------
    ssh_cmd = [
        'ssh',
        '-i', ssh_key,
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'ServerAliveInterval=5',
        f'rock64@{host}',
        f'stty -F {serial_port} {baud} raw; cat > {serial_port}',
    ]

    if dry_run:
        print("[DRY-RUN] Would open SSH pipe:")
        print(" ", " ".join(ssh_cmd))
        ssh_proc = None
    else:
        print(f"[bridge] Connecting to {host} → {serial_port} at {baud} baud...")
        try:
            ssh_proc = subprocess.Popen(
                ssh_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            print("ERROR: 'ssh' not found. Install OpenSSH or Git for Windows (which bundles ssh).")
            sys.exit(1)

        # Give SSH a moment to connect
        time.sleep(1.5)
        if ssh_proc.poll() is not None:
            err = ssh_proc.stderr.read().decode()
            print(f"ERROR: SSH connection failed:\n{err}")
            sys.exit(1)
        print("[bridge] SSH connected.")

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
    print("  Left stick Y  → forward / back")
    print("  Right stick X → turn left / right")
    print("  Press Ctrl+C to stop (sends zero-speed packet first).")
    print()

    interval = 1.0 / POLL_HZ
    last_left, last_right = None, None

    def send(left: int, right: int):
        pkt = motor_packet(1, right) + motor_packet(2, left)  # motor 1=right, 2=left
        if dry_run:
            print(f"  [dry] L={left:+4d} R={right:+4d}  →  {pkt.decode().strip()}")
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
                print(f"\r  L={left_speed:+4d} [{l_bar:<10}]   R={right_speed:+4d} [{r_bar:<10}]   ", end='', flush=True)

            elapsed = time.monotonic() - t_start
            time.sleep(max(0, interval - elapsed))

    except KeyboardInterrupt:
        print("\n\n[bridge] Stopping — sending zero speed...")
        try:
            send(0, 0)
        except Exception:
            pass

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
        description="Windows PS5 DualSense → Rock64 motor bridge (no ROS2, no WSL)"
    )
    parser.add_argument('--host', default='192.168.1.159', help='Rock64 IP address')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Serial port on Rock64')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--ssh-key', default=r'C:\Users\ZIXXE\.ssh\rock64_sync',
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
