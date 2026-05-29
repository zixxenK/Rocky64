# Rock64 Robot Architecture

This document captures the integrated architecture for the Rock64 robotics platform, based on the repository firmware, host stack, and hardware notes.

## System overview

The platform is a heterogeneous distributed robotics system:

- **Rock64 SBC**: high-level host node, serial telemetry bridge, and vision stream receiver.
- **Arduino Uno R3**: low-level real-time motor controller and heartbeat safety manager.
- **ESP32-CAM**: networked vision node delivering MJPEG video to the Rock64.
- **Primary vehicle**: Elegoo Smart Robot Car chassis with 4× DC gear motors and motor driver shield.
- **Power architecture**: separate motor and logic power rails with a common ground.

## Hardware components

### Primary edge node

- **Pine64 Rock64** (RK3328, 1.5GHz quad-core ARM Cortex-A53)
- **USB 3.0, Gigabit Ethernet, UART, HDMI** capabilities
- **40-pin header** for peripheral access

### Real-time actuator controller

- **Arduino Uno R3** with motor shield (L293D/TB6612FNG style)
- **Motor outputs** for left/right drive motors
- **Ultrasonic sensor**, **IMU**, and servo control on the shield

### Vision node

- **ESP32-CAM** with OV2640 camera
- Serves live MJPEG stream via Wi-Fi AP
- Connects to host via network rather than direct USB video when deployed

## Software architecture

### Firmware

- `firmware/mcu-motors/src/main.cpp`
  - Asynchronous serial packet parser
  - Heartbeat timeout safety
  - Motor drive commands using AFMotor
  - AVR watchdog enabled

- `firmware/esp32-vision/src/main.cpp`
  - Camera initialization and Wi-Fi AP setup
  - MJPEG stream server on `/stream`
  - PSRAM-aware configuration with fallback resolutions

### Host stack

- `ros2_ws/host_control/serial_bridge.py`
  - Sends motor commands using formatted packets like `<motor,direction,speed>`
  - Supports emergency stop

- `ros2_ws/host_control/camera_stream.py`
  - Reads camera stream asynchronously using OpenCV
  - Keeps the latest frame available for downstream processing

- `ros2_ws/host_control/main.py`
  - Smoke test harness for serial and camera integration
  - Validates that the robot can receive motor commands and deliver camera frames

### Deployment

- `deployment/rock64_setup.sh`
  - Installs Python, pip, OpenCV, Git
  - Installs the host requirements
  - Adds the user to the `dialout` group for serial access

## Communication model

### Serial messaging

- Rock64 sends commands to Arduino over UART at **115200 baud**.
- Command format: `<motorId,direction,speed>`
  - `motorId`: `0` = both, `1` = right, `2` = left
  - `direction`: `F`, `B`, or `S`
  - `speed`: `0`–`255`
- Arduino enforces a **200 ms heartbeat timeout** and stops motors if packets cease.

### Vision streaming

- ESP32-CAM hosts a Wi-Fi AP named `ESP32-CAM-AP`.
- Default stream endpoint: `http://192.168.4.1/stream`
- The host uses threaded OpenCV capture to reduce latency and always read the latest frame.

## Power and safety

- Motor power and logic power must remain isolated.
- Use one shared ground connection between the motor controller and Rock64.
- Prefer a dedicated **5V 3A** regulator for the Rock64.
- Avoid powering the ESP32-CAM from noisy motor supply rails.
- Use suppression capacitors on DC motors if needed.

## Recommended progression

1. Validate hardware wiring and grounds.
2. Flash and test the Arduino motor firmware.
3. Flash and verify the ESP32-CAM stream.
4. Run `ros2_ws/host_control/main.py` to confirm end-to-end integration.
5. Migrate the host stack into ROS 2 nodes once the hardware path is stable.

## Future architecture direction

The next design phase is to evolve the host-side Python integration into a true ROS 2 workspace, including:

- `ros2_ws/src/robot_control/`
- `ros2_ws/src/robot_msgs/`
- `ros2_ws/src/robot_bringup/`

This will allow the Rock64 to participate in a proper ROS 2 node graph while preserving the Arduino as a deterministic real-time actuator layer.
