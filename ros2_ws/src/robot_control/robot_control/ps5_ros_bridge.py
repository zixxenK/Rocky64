import argparse
import select
import sys
import time

import evdev
from evdev import InputDevice, categorize, ecodes

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.utilities import remove_ros_args
from std_msgs.msg import Int16

MAX_RATE_HZ = 20
DEADZONE = 0.2

# DualSense evdev mappings
ABS_X = ecodes.ABS_X
ABS_Y = ecodes.ABS_Y
ABS_Z = ecodes.ABS_Z          # L2
ABS_RX = ecodes.ABS_RX
ABS_RY = ecodes.ABS_RY
ABS_RZ = ecodes.ABS_RZ        # R2
ABS_HAT0X = ecodes.ABS_HAT0X  # D-Pad X
ABS_HAT0Y = ecodes.ABS_HAT0Y  # D-Pad Y

def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))

def apply_deadzone(value):
    if abs(value) <= DEADZONE:
        return 0.0
    return float(value)

def normalize_abs(value, absinfo):
    if absinfo is None or absinfo.max == absinfo.min:
        return float(value)
    center = (absinfo.max + absinfo.min) / 2.0
    normalized = 2.0 * (value - center) / float(absinfo.max - absinfo.min)
    return clamp(normalized, -1.0, 1.0)

def normalize_trigger(value, absinfo):
    if absinfo is None or absinfo.max == absinfo.min:
        return clamp(float(value), 0.0, 1.0)
    normalized = float(value - absinfo.min) / float(absinfo.max - absinfo.min)
    return clamp(normalized, 0.0, 1.0)

def compute_speed_scale(l2_value, r2_value, min_scale=0.4, max_scale=1.0):
    scale = 1.0
    if l2_value > 0.0:
        scale = max(min_scale, 1.0 - (1.0 - min_scale) * l2_value)
    if r2_value > 0.0:
        scale = max(scale, min(max_scale, 0.7 + 0.3 * r2_value))
    return clamp(scale, min_scale, max_scale)


class PS5EvdevBridge(Node):
    def __init__(self, cmd_vel_topic, camera_servo_topic, invert_lefty):
        super().__init__('ps5_ros_bridge')
        self.cmd_vel_topic = cmd_vel_topic
        self.camera_servo_topic = camera_servo_topic
        self.invert_lefty = invert_lefty

        self.pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.servo_pub = self.create_publisher(Int16, self.camera_servo_topic, 1)
        
        self.device = None
        self.abs_state = {}
        self.abs_info = {}
        self.hat_state = (0, 0)
        self.servo_position = 90
        self.last_no_subscriber_warning = 0.0

    def find_controller(self):
        devices = [InputDevice(path) for path in evdev.list_devices()]
        for dev in devices:
            if 'DualSense' in dev.name or 'Sony' in dev.name:
                self.get_logger().info(f'Found controller: {dev.name} at {dev.path}')
                self.device = dev
                self.setup_axes()
                return True
        return False

    def setup_axes(self):
        for code in (ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ, ABS_HAT0X, ABS_HAT0Y):
            try:
                self.abs_info[code] = self.device.absinfo(code)
                self.abs_state[code] = self.abs_info[code].value
            except Exception:
                self.abs_info[code] = None
                self.abs_state[code] = 0

    def read_events(self):
        if self.device is None:
            return

        try:
            r, _, _ = select.select([self.device.fd], [], [], 0)
            if r:
                # FIXED: Use a while loop with read_one() to drain the buffer without blocking
                while True:
                    event = self.device.read_one()
                    if event is None:
                        break
                    if event.type == ecodes.EV_ABS:
                        self.abs_state[event.code] = event.value
                        if event.code == ABS_HAT0X:
                            self.hat_state = (event.value, self.hat_state[1])
                        elif event.code == ABS_HAT0Y:
                            self.hat_state = (self.hat_state[0], event.value)
        except OSError:
            self.get_logger().error('Controller disconnected!')
            self.device = None

    def run(self):
        self.get_logger().info('Starting PS5 evdev bridge. Waiting for controller...')
        rate = self.create_rate(MAX_RATE_HZ)
        last_hat = (0, 0)

        while rclpy.ok():
            if self.device is None:
                if not self.find_controller():
                    time.sleep(2.0)
                    continue

            self.read_events()

            if self.device is not None:
                leftx = normalize_abs(self.abs_state.get(ABS_X, 0), self.abs_info.get(ABS_X))
                lefty = normalize_abs(self.abs_state.get(ABS_Y, 0), self.abs_info.get(ABS_Y))
                rightx = normalize_abs(self.abs_state.get(ABS_RX, 0), self.abs_info.get(ABS_RX))

                l2 = normalize_trigger(self.abs_state.get(ABS_Z, 0), self.abs_info.get(ABS_Z))
                r2 = normalize_trigger(self.abs_state.get(ABS_RZ, 0), self.abs_info.get(ABS_RZ))

                twist = Twist()
                forward = -apply_deadzone(lefty) if not self.invert_lefty else apply_deadzone(lefty)
                turn = -apply_deadzone(rightx)

                speed_scale = compute_speed_scale(l2, r2)
                twist.linear.x = forward * speed_scale
                twist.angular.z = turn * speed_scale

                self.pub.publish(twist)
                self._warn_if_unsubscribed()

                # Show numbers flying by whenever sticks are pushed out of the deadzone
                if twist.linear.x != 0.0 or twist.angular.z != 0.0:
                    self.get_logger().info(f"Drive Command -> Linear X: {twist.linear.x:.2f}, Angular Z: {twist.angular.z:.2f}")

                hat = self.hat_state
                if hat != last_hat:
                    if hat[0] < 0:
                        self.servo_position = max(0, self.servo_position - 5)
                        self.servo_pub.publish(Int16(data=self.servo_position))
                        self.get_logger().info(f"Servo Pos: {self.servo_position}")
                    elif hat[0] > 0:
                        self.servo_position = min(180, self.servo_position + 5)
                        self.servo_pub.publish(Int16(data=self.servo_position))
                        self.get_logger().info(f"Servo Pos: {self.servo_position}")
                    last_hat = hat

            rate.sleep()

    def _warn_if_unsubscribed(self):
        if self.pub.get_subscription_count() > 0:
            return

        now = time.monotonic()
        if now - self.last_no_subscriber_warning < 5.0:
            return

        self.last_no_subscriber_warning = now
        self.get_logger().warn(
            f'No subscribers on {self.cmd_vel_topic}. '
            'Start the Rock64 hardware bridge and confirm both machines '
            'share the same ROS_DOMAIN_ID.'
        )

def main(argv=None):
    rclpy.init(args=argv)
    ros_args = remove_ros_args(sys.argv)
    parser = argparse.ArgumentParser(description='PS5 DualSense to ROS2 cmd_vel bridge (evdev only)')
    parser.add_argument('--cmd-vel-topic', default='/cmd_vel')
    parser.add_argument('--camera-servo-topic', default='/camera_servo')
    parser.add_argument('--invert-lefty', action='store_true')
    args, _ = parser.parse_known_args(ros_args[1:])

    node = PS5EvdevBridge(
        cmd_vel_topic=args.cmd_vel_topic,
        camera_servo_topic=args.camera_servo_topic,
        invert_lefty=args.invert_lefty
    )

    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        # Emergency stop before shutdown
        twist = Twist()
        twist.linear.x = 0.0
        twist.angular.z = 0.0
        node.pub.publish(twist)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
