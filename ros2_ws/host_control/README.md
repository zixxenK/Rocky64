# Rock64 Host Control Setup

This directory contains the Python host control integration code for the Rock64 robot.

## Overview
This host stack is a diagnostic and smoke-test helper for validating the Rock64
robot hardware path before or alongside the ROS 2 bringup.

For the preferred runtime entrypoints, use the ROS 2 launch files in
`ros2_ws/src/robot_bringup`.

The current host stack validates basic robot integration by doing both:

- sending motor commands to the Arduino Uno over UART
- reading the ESP32-CAM MJPEG stream over HTTP

## Install dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-opencv git
cd ~/Rock64\ Robot/ros2_ws
python3 -m pip install -r requirements.txt
```

## Serial access setup

Add the current user to the serial group so `/dev/ttyACM0` is accessible:

```bash
sudo usermod -a -G dialout $USER
```

Then log out and log back in.

## Run the smoke test

From `ros2_ws/`:

```bash
python3 host_control/main.py --serial-port /dev/ttyACM0 --camera-ip 192.168.4.1
```

The script performs repeated motor commands and checks whether the camera stream returns frames.

## Stream diagnostics

If the camera stream is unstable, use the diagnostics helper from `ros2_ws/`:

```bash
python3 host_control/stream_diagnostics.py --camera-ip 192.168.4.1
```

This checks the `/status`, single-frame `/jpg`, and MJPEG `/stream` endpoints and reports response details.

If you are placing the ESP32-CAM in station mode, replace `192.168.4.1` with the DHCP IP assigned by your router.

## Fresh-start preflight

Use the preflight helper before launching ROS 2 nodes to confirm the exact
camera, serial, and environment assumptions for the host you are on.

Rock64 example:

```bash
cd ~/Rock64\ Robot/ros2_ws
python3 host_control/bringup_preflight.py \
	--role rock64 \
	--network-mode station \
	--expected-ssid TELUS4424 \
	--camera-ip <esp32-dhcp-ip>
```

Local PC example:

```bash
cd ~/Rock64\ Robot/ros2_ws
python3 host_control/bringup_preflight.py \
	--role pc \
	--network-mode station \
	--expected-ssid TELUS4424 \
	--camera-ip <esp32-dhcp-ip> \
	--robot-host <rock64-lan-ip>
```

If the ESP32 falls back to AP mode, omit `--camera-ip` or set it to
`192.168.4.1` and use `--network-mode ap`.

## Expected behavior
- The Arduino should receive packets like `<1,F,64>` and `<2,S,0>`.
- The ESP32-CAM should serve MJPEG frames from `http://192.168.4.1/stream`.
- If the camera is not in AP mode, use the correct IP assigned by your access point.

## Troubleshooting
- If the serial port fails, verify the device path and dialout permissions.
- If the camera cannot be opened in AP mode, confirm the ESP32-CAM AP exists and `robot2026` is the Wi-Fi password.
- If the camera is meant to be on `TELUS4424`, confirm its DHCP IP from the router or the ESP32 serial `/status` output before launching the ROS 2 stack.
- If the ESP32-CAM AP is not visible, open a serial monitor on the ESP32 board at `115200` and reset it.
- If the monitor prints `ESP-ROM:esp32s3...`, the board is in flash mode. Release `IO0` from GND and reset normally.
- If frames are not received, check the ESP32-CAM console output and Wi-Fi connectivity.

## Deployment helper
The host setup script is available at `deployment/rock64_setup.sh`.
Use it to install packages and configure the Rock64 user for serial access.
