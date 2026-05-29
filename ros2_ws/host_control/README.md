# Rock64 Host Control Setup

This directory contains the Python host control integration code for the Rock64 robot.

## Overview
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

Add the current user to the serial group so `/dev/ttyS1` is accessible:

```bash
sudo usermod -a -G dialout $USER
```

Then log out and log back in.

## Run the smoke test

From `ros2_ws/`:

```bash
python3 host_control/main.py --serial-port /dev/ttyS1 --camera-ip 192.168.4.1
```

The script performs repeated motor commands and checks whether the camera stream returns frames.

## Expected behavior
- The Arduino should receive packets like `<1,F,64>` and `<2,S,0>`.
- The ESP32-CAM should serve MJPEG frames from `http://192.168.4.1/stream`.
- If the camera is not in AP mode, use the correct IP assigned by your access point.

## Troubleshooting
- If the serial port fails, verify the device path and dialout permissions.
- If the camera cannot be opened, confirm the ESP32-CAM AP exists and `robot2026` is the Wi-Fi password.
- If the ESP32-CAM AP is not visible, open a serial monitor on the ESP32 board at `115200` and reset it.
- If the monitor prints `ESP-ROM:esp32s3...`, the board is in flash mode. Release `IO0` from GND and reset normally.
- If frames are not received, check the ESP32-CAM console output and Wi-Fi connectivity.

## Deployment helper
The host setup script is available at `deployment/rock64_setup.sh`.
Use it to install packages and configure the Rock64 user for serial access.
