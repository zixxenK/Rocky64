#!/usr/bin/env python3
"""
PS5 DualSense ROS1 bridge.

This node reads a DualSense controller via pygame and publishes geometry_msgs/Twist
messages to /cmd_vel or a custom topic.
"""

import argparse
import sys
import time

try:
    import pygame
except ImportError:
    print("Missing dependency: pip install pygame")
    sys.exit(1)

import rospy
from geometry_msgs.msg import Twist

MAX_RATE_HZ = 20
DEADZONE = 0.2


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def axis_value(value):
    if abs(value) <= DEADZONE:
        return 0.0
    return float(value)


def list_joysticks():
    return [pygame.joystick.Joystick(i).get_name() for i in range(pygame.joystick.get_count())]


def find_joystick(index=None, name=None):
    count = pygame.joystick.get_count()
    if count == 0:
        return None

    if index is not None and 0 <= index < count:
        joystick = pygame.joystick.Joystick(index)
        joystick.init()
        if name is None or joystick.get_name() == name:
            return joystick

    for i in range(count):
        joystick = pygame.joystick.Joystick(i)
        joystick.init()
        if name is None or joystick.get_name() == name:
            return joystick

    return None


def wait_for_joystick(index=None, name=None, poll_interval=2.0):
    while not rospy.is_shutdown():
        pygame.event.pump()
        joystick = find_joystick(index=index, name=name)
        if joystick is not None:
            return joystick

        controller_names = list_joysticks()
        if controller_names:
            rospy.loginfo('Found controllers: %s, waiting for match...', controller_names)
        else:
            rospy.loginfo('No controller found. Plug in or pair your DualSense and wait...')
        time.sleep(poll_interval)

    return None


def get_joystick_info(joystick):
    return {
        'name': joystick.get_name(),
        'axes': joystick.get_numaxes(),
        'buttons': joystick.get_numbuttons(),
        'hats': joystick.get_numhats(),
    }


def build_twist(leftx, lefty, invert_lefty=False):
    twist = Twist()
    forward = -axis_value(lefty) if not invert_lefty else axis_value(lefty)
    turn = axis_value(leftx)

    twist.linear.x = forward
    twist.angular.z = turn
    return twist


def main():
    parser = argparse.ArgumentParser(description='PS5 DualSense to ROS1 cmd_vel bridge')
    parser.add_argument('--cmd-vel-topic', default='/cmd_vel', help='ROS topic to publish Twist messages')
    parser.add_argument('--joystick-index', type=int, default=None, help='Controller index if multiple gamepads are connected')
    parser.add_argument('--controller-name', default=None, help='Optional controller name filter')
    parser.add_argument('--poll-interval', type=float, default=2.0, help='Seconds between controller detection retries')
    parser.add_argument('--leftx-axis', type=int, default=0, help='Axis index for left stick horizontal')
    parser.add_argument('--lefty-axis', type=int, default=1, help='Axis index for left stick vertical')
    parser.add_argument('--invert-lefty', action='store_true', help='Invert the left stick vertical axis')

    ros_args = rospy.myargv(argv=sys.argv)[1:]
    ros_args = [arg for arg in ros_args if not arg.startswith('__')]
    args = parser.parse_args(ros_args)

    rospy.init_node('ps5_ros_bridge', anonymous=False)
    pub = rospy.Publisher(args.cmd_vel_topic, Twist, queue_size=10)

    pygame.init()
    pygame.joystick.init()

    joystick = wait_for_joystick(index=args.joystick_index, name=args.controller_name, poll_interval=args.poll_interval)
    if joystick is None:
        rospy.logerr('Controller wait terminated before connection.')
        return

    info = get_joystick_info(joystick)
    rospy.loginfo('Using controller: %s', info['name'])
    rospy.loginfo('Joystick axes: %d buttons: %d hats: %d', info['axes'], info['buttons'], info['hats'])
    rospy.loginfo('Publishing Twist to %s', args.cmd_vel_topic)
    rospy.loginfo('Left stick axes: leftx=%d lefty=%d invert=%s', args.leftx_axis, args.lefty_axis, args.invert_lefty)

    rate = rospy.Rate(MAX_RATE_HZ)

    try:
        while not rospy.is_shutdown():
            pygame.event.pump()
            if not joystick.get_init():
                joystick = wait_for_joystick(index=args.joystick_index, name=args.controller_name, poll_interval=args.poll_interval)
                if joystick is None:
                    break
                rospy.loginfo('Reconnected to controller: %s', joystick.get_name())

            leftx = joystick.get_axis(args.leftx_axis)
            lefty = joystick.get_axis(args.lefty_axis)
            twist = build_twist(leftx, lefty, invert_lefty=args.invert_lefty)
            pub.publish(twist)
            rate.sleep()
    except rospy.ROSInterruptException:
        pass
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
