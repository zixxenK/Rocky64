import argparse
import sys
import time

try:
    import pygame
except ImportError:
    print('Missing dependency: pip install pygame')
    raise

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


class KeyboardTeleop(Node):
    def __init__(
        self,
        cmd_vel_topic: str,
        camera_servo_topic: str,
        linear_speed: float,
        angular_speed: float,
        publish_rate: float,
        servo_step: int,
        servo_repeat_hz: float,
    ):
        super().__init__('keyboard_teleop')
        self.cmd_vel_topic = cmd_vel_topic
        self.camera_servo_topic = camera_servo_topic
        self.linear_speed = linear_speed
        self.angular_speed = angular_speed
        self.publish_rate = publish_rate
        self.servo_step = servo_step
        self.servo_repeat_hz = servo_repeat_hz

        self.cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.camera_servo_pub = self.create_publisher(
            Int16,
            self.camera_servo_topic,
            10,
        )

        self.servo_position = 90
        self.last_servo_update = 0.0

    def run(self) -> None:
        pygame.init()
        pygame.display.set_caption('Rock64 Keyboard Teleop')
        screen = pygame.display.set_mode((540, 180))
        font = pygame.font.Font(None, 28)
        clock = pygame.time.Clock()

        self.camera_servo_pub.publish(Int16(data=self.servo_position))
        self.get_logger().info(
            'Keyboard teleop started. Focus the pygame window and use '
            'WASD for drive, Q/E for camera servo, Esc to quit.'
        )

        try:
            while rclpy.ok():
                should_exit = self._process_events()
                keys = pygame.key.get_pressed()

                twist = Twist()
                twist.linear.x, twist.angular.z = compute_twist_components(
                    forward=keys[pygame.K_w],
                    backward=keys[pygame.K_s],
                    turn_left=keys[pygame.K_a],
                    turn_right=keys[pygame.K_d],
                    linear_speed=self.linear_speed,
                    angular_speed=self.angular_speed,
                )
                self.cmd_vel_pub.publish(twist)

                self._update_servo(keys)
                self._draw_status(screen, font, twist)

                if should_exit:
                    break

                clock.tick(self.publish_rate)
        finally:
            self.cmd_vel_pub.publish(Twist())
            pygame.quit()

    def _process_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return True
        return False

    def _update_servo(self, keys) -> None:
        move_left = keys[pygame.K_q]
        move_right = keys[pygame.K_e]
        if not move_left and not move_right:
            return

        now = time.monotonic()
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
        self.get_logger().info(
            'Camera servo target -> %d',
            self.servo_position,
        )

    def _draw_status(self, screen, font, twist: Twist) -> None:
        screen.fill((24, 26, 27))
        lines = [
            'W/S: forward/back   A/D: turn   Q/E: camera servo   Esc: quit',
            (
                f'cmd_vel -> linear.x={twist.linear.x:.2f} '
                f'angular.z={twist.angular.z:.2f}'
            ),
            f'camera_servo -> {self.servo_position}',
            f'topics -> {self.cmd_vel_topic} | {self.camera_servo_topic}',
        ]

        y = 24
        for line in lines:
            surface = font.render(line, True, (235, 235, 235))
            screen.blit(surface, (18, y))
            y += 34

        pygame.display.flip()


def main(argv=None):
    rclpy.init(args=argv)
    ros_args = remove_ros_args(sys.argv if argv is None else argv)

    parser = argparse.ArgumentParser(
        description=(
            'Keyboard teleop for Rock64 robot with camera servo output'
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
    args, _unknown = parser.parse_known_args(ros_args[1:])

    node = KeyboardTeleop(
        cmd_vel_topic=args.cmd_vel_topic,
        camera_servo_topic=args.camera_servo_topic,
        linear_speed=args.linear_speed,
        angular_speed=args.angular_speed,
        publish_rate=args.publish_rate,
        servo_step=args.servo_step,
        servo_repeat_hz=args.servo_repeat_hz,
    )

    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
