"""Headless keyboard teleop — drives the robot from a plain terminal.

Unlike ``keyboard_teleop`` (which opens a pygame/SDL window and therefore
needs a display server), this node reads keystrokes straight from stdin in
raw mode. It needs no X server, so it works in a bare WSL terminal, over
SSH, or anywhere ``$DISPLAY`` is unavailable.

Controls match the windowed version:
    W/S  forward / backward      A/D  turn left / right
    Q/E  camera servo left/right Space (or K)  stop now
    Esc (or Ctrl-C)  quit

Drive keys use the terminal's auto-repeat plus a short hold timeout, so
holding a key keeps the robot moving and releasing it stops shortly after.
"""
import argparse
import select
import sys
import termios
import time
import tty

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.utilities import remove_ros_args
from std_msgs.msg import Int16
from robot_control.keyboard_mapping import DEFAULT_ANGULAR_SPEED
from robot_control.keyboard_mapping import DEFAULT_LINEAR_SPEED
from robot_control.keyboard_mapping import DEFAULT_SERVO_STEP
from robot_control.keyboard_mapping import compute_twist_components
from robot_control.keyboard_mapping import next_servo_position

DEFAULT_PUBLISH_RATE = 20.0
DEFAULT_SERVO_REPEAT_HZ = 8.0
DEFAULT_HOLD_TIMEOUT = 0.4

DRIVE_KEYS = ('w', 'a', 's', 'd')
SERVO_KEYS = ('q', 'e')
STOP_KEYS = (' ', 'k')


def key_held(press_times: dict, key: str, now: float, timeout: float) -> bool:
    """Whether ``key`` counts as held given its last-press time.

    A key is "held" for ``timeout`` seconds after it was last seen. Terminal
    auto-repeat re-sends the character while the physical key is down, so a
    timeout slightly larger than the repeat interval yields hold-to-move
    behaviour without any key-up event (terminals don't emit one).
    """
    last = press_times.get(key)
    if last is None:
        return False
    if timeout <= 0:
        return False
    return (now - last) < timeout


class KeyboardTerminalTeleop(Node):
    def __init__(
        self,
        cmd_vel_topic: str,
        camera_servo_topic: str,
        linear_speed: float,
        angular_speed: float,
        publish_rate: float,
        servo_step: int,
        servo_repeat_hz: float,
        hold_timeout: float,
    ):
        super().__init__('keyboard_terminal_teleop')
        self.cmd_vel_topic = cmd_vel_topic
        self.camera_servo_topic = camera_servo_topic
        self.linear_speed = linear_speed
        self.angular_speed = angular_speed
        self.publish_rate = publish_rate if publish_rate > 0 else 20.0
        self.servo_step = servo_step
        self.servo_repeat_hz = servo_repeat_hz
        self.hold_timeout = hold_timeout

        self.cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.camera_servo_pub = self.create_publisher(
            Int16,
            self.camera_servo_topic,
            10,
        )

        self.servo_position = 90
        self.last_servo_update = 0.0
        self.press_times: dict = {}

    def run(self) -> None:
        self.camera_servo_pub.publish(Int16(data=self.servo_position))
        self._print_banner()

        stdin_fd = sys.stdin.fileno()
        old_attrs = termios.tcgetattr(stdin_fd)
        period = 1.0 / self.publish_rate
        try:
            tty.setcbreak(stdin_fd)
            while rclpy.ok():
                if self._drain_input():
                    break
                now = time.monotonic()
                twist = self._build_twist(now)
                self.cmd_vel_pub.publish(twist)
                self._update_servo(now)
                self._draw_status(twist)
                time.sleep(period)
        finally:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_attrs)
            self.cmd_vel_pub.publish(Twist())
            sys.stdout.write('\r\n')
            sys.stdout.flush()

    def _drain_input(self) -> bool:
        """Read all pending keystrokes. Returns True if quit was requested."""
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if not ready:
                return False
            ch = sys.stdin.read(1)
            if ch == '':
                return True
            # Lone Esc quits; longer escape sequences (arrow keys) are ignored
            # so a stray arrow press doesn't kill the session.
            if ch == '\x1b':
                tail, _, _ = select.select([sys.stdin], [], [], 0)
                if not tail:
                    return True
                sys.stdin.read(1)
                continue
            lower = ch.lower()
            if lower in STOP_KEYS:
                self.press_times.clear()
                continue
            if lower in DRIVE_KEYS or lower in SERVO_KEYS:
                self.press_times[lower] = time.monotonic()

    def _build_twist(self, now: float) -> Twist:
        twist = Twist()
        twist.linear.x, twist.angular.z = compute_twist_components(
            forward=key_held(self.press_times, 'w', now, self.hold_timeout),
            backward=key_held(self.press_times, 's', now, self.hold_timeout),
            turn_left=key_held(self.press_times, 'a', now, self.hold_timeout),
            turn_right=key_held(self.press_times, 'd', now, self.hold_timeout),
            linear_speed=self.linear_speed,
            angular_speed=self.angular_speed,
        )
        return twist

    def _update_servo(self, now: float) -> None:
        move_left = key_held(self.press_times, 'q', now, self.hold_timeout)
        move_right = key_held(self.press_times, 'e', now, self.hold_timeout)
        if not move_left and not move_right:
            return

        interval = (
            1.0 / self.servo_repeat_hz if self.servo_repeat_hz > 0 else 0.0
        )
        if interval > 0 and now - self.last_servo_update < interval:
            return

        new_position = next_servo_position(
            self.servo_position,
            move_left=move_left,
            move_right=move_right,
            step=self.servo_step,
        )
        if new_position == self.servo_position:
            return

        self.servo_position = new_position
        self.last_servo_update = now
        self.camera_servo_pub.publish(Int16(data=self.servo_position))

    def _print_banner(self) -> None:
        self.get_logger().info(
            'Headless keyboard teleop started (no display required). '
            'Keep this terminal focused.'
        )
        sys.stdout.write(
            '\r\n'
            'Rock64 terminal teleop — no display needed\r\n'
            '  W/S forward/back   A/D turn   Q/E camera servo\r\n'
            '  Space or K stop    Esc or Ctrl-C quit\r\n'
            f'  topics: {self.cmd_vel_topic} | {self.camera_servo_topic}\r\n'
            '\r\n'
        )
        sys.stdout.flush()

    def _draw_status(self, twist: Twist) -> None:
        sys.stdout.write(
            '\r'
            f'cmd_vel linear.x={twist.linear.x:+.2f} '
            f'angular.z={twist.angular.z:+.2f}  '
            f'servo={self.servo_position:3d}   '
        )
        sys.stdout.flush()


def main(argv=None):
    rclpy.init(args=argv)
    ros_args = remove_ros_args(sys.argv if argv is None else argv)

    parser = argparse.ArgumentParser(
        description=(
            'Headless terminal keyboard teleop for Rock64 robot '
            '(no display required)'
        ),
    )
    parser.add_argument('--cmd-vel-topic', default='cmd_vel')
    parser.add_argument('--camera-servo-topic', default='camera_servo')
    parser.add_argument(
        '--linear-speed',
        type=float,
        default=DEFAULT_LINEAR_SPEED,
    )
    parser.add_argument(
        '--angular-speed',
        type=float,
        default=DEFAULT_ANGULAR_SPEED,
    )
    parser.add_argument(
        '--publish-rate',
        type=float,
        default=DEFAULT_PUBLISH_RATE,
    )
    parser.add_argument('--servo-step', type=int, default=DEFAULT_SERVO_STEP)
    parser.add_argument(
        '--servo-repeat-hz',
        type=float,
        default=DEFAULT_SERVO_REPEAT_HZ,
    )
    parser.add_argument(
        '--hold-timeout',
        type=float,
        default=DEFAULT_HOLD_TIMEOUT,
    )
    args, _unknown = parser.parse_known_args(ros_args[1:])

    if not sys.stdin.isatty():
        print(
            'keyboard_terminal_teleop needs an interactive terminal (a TTY) '
            'for stdin. Run it directly in a terminal, not through a pipe or '
            'a launch file with output redirected.',
            file=sys.stderr,
        )
        rclpy.shutdown()
        return

    node = KeyboardTerminalTeleop(
        cmd_vel_topic=args.cmd_vel_topic,
        camera_servo_topic=args.camera_servo_topic,
        linear_speed=args.linear_speed,
        angular_speed=args.angular_speed,
        publish_rate=args.publish_rate,
        servo_step=args.servo_step,
        servo_repeat_hz=args.servo_repeat_hz,
        hold_timeout=args.hold_timeout,
    )

    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
