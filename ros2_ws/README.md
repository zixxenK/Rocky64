# ROS 2 Workspace Placeholder

This folder contains a future ROS2 integration scaffold for the Rock64 robotics platform.
The active current integration is ROS1 Noetic in `ros1_ws`.

## Current implementation
The first layer of host integration is a lightweight Python-based controller for Rock64 hardware.

- `host_control/serial_bridge.py` — sends motor control packets to the Arduino Uno over UART.
- `host_control/camera_stream.py` — reads the ESP32-CAM MJPEG stream asynchronously using OpenCV.
- `host_control/main.py` — a smoke-test harness that validates serial and camera integration.
- `requirements.txt` — Python dependencies for the host control stack.

## Architecture
The system currently uses a split architecture:

- **Rock64** handles high-level coordination and stream ingestion.
- **Arduino Uno** handles low-latency motor actuation and heartbeat safety.
- **ESP32-CAM** provides the vision stream via Wi-Fi.

This repository is designed to evolve into a proper ROS 2 workspace once hardware integration is stable.

A new ROS 2 package scaffold has been added at `ros2_ws/src/robot_control` for the future ROS 2 node implementation.

## Install dependencies
From `ros2_ws/`:

```bash
python3 -m pip install -r requirements.txt
```

## Run the host control smoke test

```bash
python3 host_control/main.py --serial-port /dev/ttyS1 --camera-ip 192.168.4.1
```

### Recommended runtime flags
- `--serial-port /dev/ttyS1`
- `--baudrate 115200`
- `--camera-ip 192.168.4.1`
- `--camera-port 80`

## Run the ROS 2 robot control node

From `ros2_ws/`:

```bash
source /opt/ros/<distro>/setup.bash
colcon build --packages-select robot_control
source install/setup.bash
ros2 run robot_control robot_control_node --ros-args \
  -p serial_port:=/dev/ttyS1 \
  -p baudrate:=115200 \
  -p camera_ip:=192.168.4.1 \
  -p camera_port:=80
```

The ROS 2 node publishes `robot_telemetry` and `camera_status` topics while subscribing to `cmd_vel`.

## Notes
- The current host control stack is intentionally minimal and Python-based.
- `ros2_ws/` is a placeholder for future ROS 2 packages such as `robot_control`, `robot_msgs`, and `robot_bringup`.
- The ESP32-CAM stream is expected at `http://192.168.4.1/stream` in AP mode.
- The Arduino should be connected to the Rock64 serial interface, typically `/dev/ttyS1`.

## Rock64 setup
- Use `deployment/rock64_setup.sh` to install dependencies and add the user to the `dialout` group.
- After running the setup script, log out and log back in to apply serial group permissions.

## Next steps
1. Confirm the ESP32- CAM AP and stream are accessible on the Rock64.
2. Confirm the Arduino receives serial commands and stops motors on heartbeat loss.
3. Migrate this integration layer into ROS 2 nodes once the hardware path is proven.