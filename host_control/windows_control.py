#!/usr/bin/env python3
"""windows_control.py - unified Windows control for the Rock64 robot.

One tool, two input sources, switchable on the fly while driving:

  * PS5 DualSense controller (via pygame)
  * PC keyboard (WASD) - read straight from the console, no window needed

It speaks the exact same ``<id,dir,spd>`` / ``<SERVO,pos>`` serial packets as
``arduino_serial_bridge`` and pipes them to the Rock64's serial port over a
persistent SSH connection. **No ROS 2 is required on the PC** - this is the
Windows-native path.

Usage:
  python host_control/windows_control.py --host 192.168.1.159
  python host_control/windows_control.py --source keyboard
  python host_control/windows_control.py --list-joysticks
  python host_control/windows_control.py --dry-run

Controls:
  Tab                     switch input source (controller <-> keyboard)
  Keyboard:  W / S        forward / backward
             A / D        turn left / right
             Q / E        camera servo left / right
             Space / K    stop now
             Esc / Ctrl-C quit (sends a stop first)
  Controller: left stick Y  drive,   right stick X  turn
              L1 / R1       camera servo,   Options/Start  quit

Requirements (install in **Windows** Python, not WSL):
  pip install pygame          # controller support
  # keyboard uses the stdlib `msvcrt`; SSH uses the bundled `ssh`
"""

import argparse
import sys
import time

from ps5_windows_bridge import (
    POLL_HZ,
    apply_deadzone,
    list_joysticks,
    motor_packet,
    open_ssh_pipe,
    twist_to_wheel_speeds,
)

# Keyboard tuning -------------------------------------------------------------
KEY_DRIVE_SCALE = 0.85   # fraction of full speed for a held W/S
KEY_TURN_SCALE = 0.70    # fraction of full turn for a held A/D
HOLD_TIMEOUT = 0.4       # a key counts as "held" this long after its last press
SERVO_STEP = 5           # degrees per servo nudge
SERVO_MIN, SERVO_MAX = 0, 180
SERVO_REPEAT_HZ = 8.0    # how fast the servo sweeps while Q/E is held

DRIVE_KEYS = ('w', 'a', 's', 'd')
SERVO_KEYS = ('q', 'e')
STOP_KEYS = (' ', 'k')


def servo_packet(position: int) -> bytes:
    """Format: ``<SERVO,position>\\n`` - same as arduino_serial_bridge."""
    return f'<SERVO,{int(position)}>\n'.encode()


def key_held(press_times: dict, key: str, now: float) -> bool:
    """Whether ``key`` was pressed within ``HOLD_TIMEOUT`` seconds.

    The OS console auto-repeats a held key, so a timeout slightly larger than
    the repeat interval gives hold-to-move behaviour without any key-up event
    (consoles don't emit one).
    """
    last = press_times.get(key)
    if last is None:
        return False
    return (now - last) < HOLD_TIMEOUT


class KeyboardReader:
    """Non-blocking console keyboard reader (Windows ``msvcrt``)."""

    def __init__(self):
        import msvcrt  # Windows-only; imported lazily so the file loads anywhere
        self._msvcrt = msvcrt

    def poll(self):
        """Drain pending keystrokes. Returns a list of single characters."""
        out = []
        while self._msvcrt.kbhit():
            ch = self._msvcrt.getwch()
            # Arrow / function keys arrive as a two-char sequence with a
            # '\x00' or '\xe0' prefix; swallow the scan code and ignore them.
            if ch in ('\x00', '\xe0'):
                if self._msvcrt.kbhit():
                    self._msvcrt.getwch()
                continue
            out.append(ch)
        return out


class Controller:
    """PS5 DualSense source backed by pygame."""

    def __init__(self, joystick_index, lefty_axis, rightx_axis,
                 l1_button, r1_button, quit_button):
        import pygame
        self._pygame = pygame
        self.lefty_axis = lefty_axis
        self.rightx_axis = rightx_axis
        self.l1_button = l1_button
        self.r1_button = r1_button
        self.quit_button = quit_button

        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise RuntimeError("No joystick detected by pygame.")
        if joystick_index >= pygame.joystick.get_count():
            raise RuntimeError(
                f"Joystick index {joystick_index} requested but only "
                f"{pygame.joystick.get_count()} found."
            )
        self.js = pygame.joystick.Joystick(joystick_index)
        self.js.init()

    @property
    def name(self):
        return self.js.get_name()

    def _button(self, idx):
        if idx < 0 or idx >= self.js.get_numbuttons():
            return False
        return bool(self.js.get_button(idx))

    def read(self):
        """Return ``(linear, angular, servo_delta, quit)`` for this tick."""
        self._pygame.event.pump()
        raw_linear = self.js.get_axis(self.lefty_axis)
        raw_angular = self.js.get_axis(self.rightx_axis)
        linear = -apply_deadzone(raw_linear)   # up = forward
        angular = -apply_deadzone(raw_angular)  # right = turn right
        servo_delta = 0
        if self._button(self.l1_button):
            servo_delta -= SERVO_STEP
        if self._button(self.r1_button):
            servo_delta += SERVO_STEP

        # Debug: print raw axis values if they're non-zero
        if abs(raw_linear) > 0.01 or abs(raw_angular) > 0.01:
            print(f"[DEBUG] Raw axis: L={raw_linear:+.3f}, R={raw_angular:+.3f} -> linear={linear:+.3f}, angular={angular:+.3f}")

        return linear, angular, servo_delta, self._button(self.quit_button)

    def close(self):
        try:
            self._pygame.quit()
        except Exception:
            pass


def compute_keyboard_drive(press_times, now):
    """Map held WASD keys to normalised ``(linear, angular)`` in [-1, 1]."""
    linear = 0.0
    angular = 0.0
    if key_held(press_times, 'w', now):
        linear += KEY_DRIVE_SCALE
    if key_held(press_times, 's', now):
        linear -= KEY_DRIVE_SCALE
    # Match the controller convention: turning right => negative angular.
    if key_held(press_times, 'd', now):
        angular -= KEY_TURN_SCALE
    if key_held(press_times, 'a', now):
        angular += KEY_TURN_SCALE
    return linear, angular


def run(host, serial_port, baud, ssh_key, source, joystick_index,
        lefty_axis, rightx_axis, l1_button, r1_button, quit_button, dry_run):
    ssh_proc = open_ssh_pipe(host, serial_port, baud, ssh_key, dry_run)

    def send(data: bytes):
        if dry_run or ssh_proc is None:
            return
        # Check if SSH process is still alive
        if ssh_proc.poll() is not None:
            print("\nERROR: SSH process died. Is the Rock64 still reachable?")
            raise BrokenPipeError("SSH process died")
        try:
            ssh_proc.stdin.write(data)
            ssh_proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            print(f"\nERROR: SSH pipe closed: {e}. Is the Rock64 still reachable?")
            raise

    def send_drive(left: int, right: int):
        # motor 1 = right, motor 2 = left (matches arduino_serial_bridge)
        send(motor_packet(1, right) + motor_packet(2, left))

    # ---- Set up input sources ----------------------------------------------
    controller = None
    keyboard = None

    def try_make_controller():
        try:
            return Controller(joystick_index, lefty_axis, rightx_axis,
                              l1_button, r1_button, quit_button)
        except Exception as exc:
            print(f"[control] Controller unavailable: {exc}")
            return None

    if source in ('auto', 'controller'):
        controller = try_make_controller()
    try:
        keyboard = KeyboardReader()
    except Exception as exc:
        print(f"[control] Keyboard input unavailable ({exc}).")

    if source == 'controller':
        mode = 'controller'
    elif source == 'keyboard':
        mode = 'keyboard'
    else:  # auto
        mode = 'controller' if controller is not None else 'keyboard'

    if mode == 'controller' and controller is None:
        if keyboard is None:
            print("ERROR: neither a controller nor keyboard input is available.")
            sys.exit(1)
        mode = 'keyboard'

    print()
    print("=========================================================")
    print("  Rock64 unified control  (PS5 controller + WASD keyboard)")
    print("=========================================================")
    if controller is not None:
        print(f"  Controller : {controller.name}")
    print(f"  Active mode: {mode.upper()}")
    print("  Tab = switch source   Space = stop   Esc/Ctrl-C = quit")
    print("  Keyboard: W/S drive  A/D turn  Q/E servo")
    print("  Controller: L-stick drive  R-stick turn  L1/R1 servo")
    print()

    press_times: dict = {}
    servo_position = 90
    last_servo_position = None
    last_servo_update = 0.0
    last_status = None
    interval = 1.0 / POLL_HZ

    # Centre the servo at startup.
    send(servo_packet(servo_position))

    try:
        while True:
            t_start = time.monotonic()
            now = t_start
            quit_requested = False
            servo_delta = 0

            # --- Keyboard events (always drained: Tab/stop/quit work in any mode)
            if keyboard is not None:
                for ch in keyboard.poll():
                    if ch == '\t':
                        if mode == 'keyboard' and controller is None:
                            controller = try_make_controller()
                        if mode == 'keyboard' and controller is not None:
                            mode = 'controller'
                        elif mode == 'controller':
                            mode = 'keyboard'
                        press_times.clear()
                        send_drive(0, 0)
                        print(f"\n[control] Switched to {mode.upper()} mode.")
                        last_status = None
                        continue
                    if ch in ('\x1b', '\x03'):  # Esc / Ctrl-C
                        quit_requested = True
                        continue
                    lower = ch.lower()
                    if lower in STOP_KEYS:
                        press_times.clear()
                        continue
                    if lower in DRIVE_KEYS or lower in SERVO_KEYS:
                        press_times[lower] = now

            # --- Compute drive + servo for the active source
            if mode == 'controller' and controller is not None:
                linear, angular, servo_delta, ctl_quit = controller.read()
                quit_requested = quit_requested or ctl_quit
            else:
                mode = 'keyboard'
                linear, angular = compute_keyboard_drive(press_times, now)
                if key_held(press_times, 'q', now):
                    servo_delta -= SERVO_STEP
                if key_held(press_times, 'e', now):
                    servo_delta += SERVO_STEP

            if quit_requested:
                break

            left, right = twist_to_wheel_speeds(linear, angular)
            send_drive(left, right)

            # --- Servo (rate-limited sweep while held)
            if servo_delta != 0 and (now - last_servo_update) >= (1.0 / SERVO_REPEAT_HZ):
                servo_position = int(
                    max(SERVO_MIN, min(SERVO_MAX, servo_position + servo_delta))
                )
                last_servo_update = now
            if servo_position != last_servo_position:
                send(servo_packet(servo_position))
                last_servo_position = servo_position

            # --- Status line (only when something changes)
            status = (mode, left, right, servo_position)
            if status != last_status:
                last_status = status
                l_bar = '#' * int(abs(left) / 25)
                r_bar = '#' * int(abs(right) / 25)
                src = 'PS5 ' if mode == 'controller' else 'WASD'
                line = (
                    f"\r  [{src}] L={left:+4d} [{l_bar:<10}] "
                    f"R={right:+4d} [{r_bar:<10}] servo={servo_position:3d}   "
                )
                if dry_run:
                    print(line)
                else:
                    print(line, end='', flush=True)

            elapsed = time.monotonic() - t_start
            time.sleep(max(0.0, interval - elapsed))

    except KeyboardInterrupt:
        pass
    finally:
        print("\n[control] Stopping - sending zero speed...")
        try:
            send_drive(0, 0)
        except Exception:
            pass
        if controller is not None:
            controller.close()
        if ssh_proc is not None:
            try:
                ssh_proc.stdin.close()
            except Exception:
                pass
            ssh_proc.terminate()
        print("[control] Bye.")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Unified Windows control for the Rock64 robot: PS5 DualSense OR "
            "WASD keyboard, switchable with Tab. No ROS 2 required."
        )
    )
    parser.add_argument('--host', default='192.168.1.159', help='Rock64 IP / hostname')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Serial port on the Rock64')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--ssh-key', default=r'C:\Users\ZIXXE\.ssh\rock64_sync',
                        help='Path to the SSH private key for the rock64 user')
    parser.add_argument('--source', choices=('auto', 'controller', 'keyboard'),
                        default='auto',
                        help='Initial input source (default: auto-detect a controller)')
    parser.add_argument('--joystick-index', type=int, default=0)
    parser.add_argument('--lefty-axis', type=int, default=1,
                        help='Axis index for the left stick Y (forward/back)')
    parser.add_argument('--rightx-axis', type=int, default=2,
                        help='Axis index for the right stick X (turn)')
    parser.add_argument('--l1-button', type=int, default=9,
                        help='Button index for servo-left (DualSense L1)')
    parser.add_argument('--r1-button', type=int, default=10,
                        help='Button index for servo-right (DualSense R1)')
    parser.add_argument('--quit-button', type=int, default=6,
                        help='Button index to quit (DualSense Options)')
    parser.add_argument('--list-joysticks', action='store_true',
                        help='List detected joysticks and exit')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print packets instead of sending them over SSH')
    args = parser.parse_args()

    if args.list_joysticks:
        list_joysticks()
        return

    run(
        host=args.host,
        serial_port=args.port,
        baud=args.baud,
        ssh_key=args.ssh_key,
        source=args.source,
        joystick_index=args.joystick_index,
        lefty_axis=args.lefty_axis,
        rightx_axis=args.rightx_axis,
        l1_button=args.l1_button,
        r1_button=args.r1_button,
        quit_button=args.quit_button,
        dry_run=args.dry_run,
    )


if __name__ == '__main__':
    main()
