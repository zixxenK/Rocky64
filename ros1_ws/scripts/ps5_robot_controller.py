#!/usr/bin/env python3
"""
PS5 DualSense robot controller bridge.

Requirements:
  pip install pygame

Usage:
  python3 ps5_robot_controller.py --robot-ip 192.168.4.1 --robot-port 8888

This script reads the left stick as joystick input and sends SmartRobotCar V4 command
frames as UDP packets to the ESP32 bridge.
"""

import argparse
import json
import math
import socket
import sys
import time

try:
    import pygame
except ImportError:
    print("Missing dependency: pip install pygame")
    sys.exit(1)


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
    while True:
        pygame.event.pump()
        joystick = find_joystick(index=index, name=name)
        if joystick is not None:
            return joystick

        controller_names = list_joysticks()
        if controller_names:
            print(f"Found controllers: {controller_names}, waiting for match...")
        else:
            print("No controller found. Plug in or pair your DualSense and wait...")
        time.sleep(poll_interval)

MAX_SPEED = 255
DEADZONE = 0.2
UDP_RATE_HZ = 20

DIRECTION_CODES = {
    "forward": 1,
    "backward": 2,
    "left": 3,
    "right": 4,
    "left_forward": 5,
    "left_backward": 6,
    "right_forward": 7,
    "right_backward": 8,
    "stop": 9,
}


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def axis_value(value):
    if abs(value) <= DEADZONE:
        return 0.0
    return float(value)


def build_command(direction, speed):
    return json.dumps({
        "N": 102,
        "D1": DIRECTION_CODES[direction],
        "D2": speed,
        "H": "01"
    })


def get_direction_and_speed(x, y):
    x = axis_value(x)
    y = axis_value(y)

    if x == 0.0 and y == 0.0:
        return "stop", 0

    speed = int(clamp(max(abs(x), abs(y)), 0.0, 1.0) * MAX_SPEED)
    speed = max(30, speed)

    if x != 0.0 and y != 0.0:
        if x < 0 and y < 0:
            return "left_forward", speed
        if x > 0 and y < 0:
            return "right_forward", speed
        if x < 0 and y > 0:
            return "left_backward", speed
        if x > 0 and y > 0:
            return "right_backward", speed

    if abs(y) >= abs(x):
        if y < 0:
            return "forward", speed
        return "backward", speed

    if x < 0:
        return "left", speed
    return "right", speed


def print_status(direction, speed, packet):
    sys.stdout.write(f"\rDirection: {direction:<13} Speed: {speed:<3} Packet: {packet}")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="PS5 DualSense to robot control bridge")
    parser.add_argument("--robot-ip", default="192.168.4.1", help="ESP32 bridge IP address")
    parser.add_argument("--robot-port", type=int, default=8888, help="ESP32 bridge UDP port")
    parser.add_argument("--joystick-index", type=int, default=None, help="Gamepad index if multiple controllers are connected")
    parser.add_argument("--controller-name", default=None, help="Optional controller name filter")
    parser.add_argument("--controller-poll", type=float, default=2.0, help="Seconds between controller detection retries")
    parser.add_argument("--leftx-axis", type=int, default=0, help="Axis index for left stick horizontal")
    parser.add_argument("--lefty-axis", type=int, default=1, help="Axis index for left stick vertical")
    parser.add_argument("--invert-lefty", action='store_true', help="Invert the left stick vertical axis")
    args = parser.parse_args()

    pygame.init()
    pygame.joystick.init()

    joystick = wait_for_joystick(index=args.joystick_index, name=args.controller_name, poll_interval=args.controller_poll)
    print(f"Using controller: {joystick.get_name()}")
    print("Axes: %d  Buttons: %d  Hats: %d" % (joystick.get_numaxes(), joystick.get_numbuttons(), joystick.get_numhats()))
    print("Left stick axes: leftx=%d lefty=%d invert=%s" % (args.leftx_axis, args.lefty_axis, args.invert_lefty))
    print("Left stick controls movement. Press Ctrl-C to quit.")
    print("If using Bluetooth, pair the DualSense with the Rock64 first and then run this script.")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.robot_ip, args.robot_port)

    clock = pygame.time.Clock()
    last_packet = ""

    try:
        while True:
            pygame.event.pump()
            if not joystick.get_init():
                joystick = wait_for_joystick(index=args.joystick_index, name=args.controller_name, poll_interval=args.controller_poll)
                print(f"Reconnected to controller: {joystick.get_name()}")

            leftx = joystick.get_axis(args.leftx_axis)
            lefty = joystick.get_axis(args.lefty_axis)
            if args.invert_lefty:
                lefty = -lefty

            direction, speed = get_direction_and_speed(leftx, lefty)
            packet = build_command(direction, speed)

            if packet != last_packet:
                sock.sendto(packet.encode("utf-8"), target)
                last_packet = packet

            print_status(direction, speed, packet)
            clock.tick(UDP_RATE_HZ)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
