# ROS1 Workspace for Rock64 Robot

This workspace contains the current ROS1 Noetic integration for the Rock64 robotics platform.

## Overview

- `ros1_ws/src/arduino_serial_bridge` contains a ROS node that connects to the Arduino Uno over a Rock64 serial port and publishes telemetry while subscribing to `/cmd_vel`.
- `ros1_ws/src/esp32_camera_bridge` contains a ROS node that pulls MJPEG frames from the ESP32-CAM stream and publishes `/camera/image_raw`.
- `ros1_ws/src/robot_bringup` provides a `roslaunch` file to start the full robot stack.

## Wiring

The current hardware wiring uses Rock64 GPIO/serial header pins and Arduino Uno digital pins:

- Rock64 pin `9` → Uno GND (blue cable)
- Rock64 pin `12` → Uno pin `2` (brown cable)
- Rock64 pin `14` → Uno pin `4` (white cable)

> This mapping assumes the Uno is using a serial-style GPIO pair on D2/D4. Verify TX/RX orientation and ground continuity before powering on.

## Build instructions

```bash
cd ~/ros1_ws
catkin_make
source devel/setup.bash
```

## Run the full robot stack

```bash
roslaunch robot_bringup rock64_robot.launch
```

## ROS nodes

- `arduino_serial_bridge` publishes `/robot_telemetry` and subscribes to `/cmd_vel`.
- `esp32_camera_bridge` publishes `/camera/image_raw`.

## PS5 controller bridge

Two PS5 DualSense controller bridges are available:

- `ros1_ws/scripts/ps5_robot_controller.py` — sends direct UDP packets to the ESP32 bridge.
- `ros1_ws/src/ps5_controller_bridge/scripts/ps5_ros_bridge.py` — publishes ROS1 `geometry_msgs/Twist` to `/cmd_vel`.

### Requirements

```bash
python3 -m pip install pygame
```

### Run the ROS topic bridge

```bash
source ~/ros1_ws/devel/setup.bash
rosrun ps5_controller_bridge ps5_ros_bridge.py --cmd-vel-topic /cmd_vel --leftx-axis 0 --lefty-axis 1
```

### Run the full robot stack with PS5 support

```bash
roslaunch robot_bringup rock64_robot.launch
```

This starts the Arduino serial bridge, ESP32 camera bridge, and PS5 controller ROS bridge together.

### Run the direct UDP bridge

```bash
python3 ros1_ws/scripts/ps5_robot_controller.py --robot-ip 192.168.4.1 --robot-port 8888 --leftx-axis 0 --lefty-axis 1
```

### Controller mapping notes

- The DualSense left stick is typically `leftx=a0` and `lefty=a1` on your controller.
- If your Linux input mapping differs, pass `--leftx-axis` and `--lefty-axis` with the correct axis indices.
- Use `--invert-lefty` if forward/backward feels reversed.

### Recommended connection modes

1. USB first (most stable)
   - Plug the DualSense into the Rock64 via USB.
   - The bridge will wait for the controller if it is not yet connected.

2. Bluetooth pairing second
   - Pair the DualSense using `bluetoothctl` on Rock64:
     ```bash
     bluetoothctl
     power on
     agent on
     default-agent
     scan on
     # put DualSense in pair mode
     pair <MAC_ADDRESS>
     trust <MAC_ADDRESS>
     connect <MAC_ADDRESS>
     ```
   - After pairing, the script should detect the controller when it appears.

### Notes

- The ROS bridge publishes Twist messages and integrates directly with `arduino_serial_bridge` via `/cmd_vel`.
- Use `--controller-index` or `--controller-name` if multiple gamepads are connected.
- The direct UDP bridge is still available for ESP32-only control.
