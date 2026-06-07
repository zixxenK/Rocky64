# Rock64 Robot

A teleoperated 4WD robot built on an Elegoo Smart Car chassis, controlled through
**ROS 2 Foxy**. A PS5 DualSense (or keyboard) drives the robot; an ESP32-S3 streams
video over WiFi.

> This README is an overview. For step-by-step run instructions see
> [`docs/QUICKSTART.md`](docs/QUICKSTART.md), for the system design see
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and for wiring/power safety see
> [`docs/HARDWARE_SAFETY.md`](docs/HARDWARE_SAFETY.md).

## Architecture at a glance

```
Operator PC ──PS5 @20Hz──► cmd_vel (ROS 2 DDS, shared ROS_DOMAIN_ID)
                               │
        Rock64: arduino_serial_bridge ──USB /dev/ttyUSB0 @115200── Arduino Uno
                               │                                    └─ <id,dir,spd> → motors
        Rock64: esp32_camera_bridge ◄──MJPEG over WiFi── ESP32-S3 (camera only)
```

- **Motor control runs over the single USB serial link** between the Rock64 and the
  Arduino. This is the only command path — there is intentionally no second master.
- **The ESP32-S3 is camera-only** (MJPEG stream). It does not relay motor commands.
  Wiring its UART into the Arduino in parallel with USB would create two masters on
  one serial bus (garbled packets) — don't.

## Components

| Node | Where | Role |
|------|-------|------|
| `ps5_ros_bridge` | Operator PC | DualSense → `cmd_vel` Twist @ 20 Hz |
| `arduino_serial_bridge` | Rock64 | `cmd_vel` → `<id,dir,spd>` serial packets |
| `esp32_camera_bridge` | Rock64 | ESP32 MJPEG → `sensor_msgs/Image` |
| firmware `mcu-motors/src/main.cpp` | Arduino Uno | Parse packets, drive H-bridge, 200 ms heartbeat |
| firmware `esp32-vision/src/main.cpp` | ESP32-S3 | WiFi + MJPEG camera server |

## Serial protocol (Rock64 → Arduino)

ASCII packets at 115200 baud:

```
<motor_id,direction,speed>\n
   motor_id : 1 = right, 2 = left
   direction: F forward, B backward, S stop
   speed    : 0–255 PWM
<SERVO,position>\n          # camera servo, 0–180
```

The firmware applies a **minimum-PWM floor** (`MIN_MOVE_PWM`, default 80) so low
joystick inputs don't sit below the motors' stiction threshold and just buzz.

## Quick start

```bash
# Rock64 (robot side)
cd ros2_ws
./robot_start.sh --role rock64 --serial-port /dev/ttyUSB0 --camera-ip 192.168.1.153

# Operator PC (PS5 teleop)
./robot_start.sh --role pc --robot-host 192.168.1.159 --teleop-mode ps5
```

Camera preview (no ROS needed): open `http://<esp32-ip>/stream` in a browser.

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for prerequisites, keyboard controls,
and DDS multicast troubleshooting.

## Repository layout

```
firmware/
  mcu-motors/      PlatformIO project for the Arduino Uno (src/main.cpp)
  esp32-vision/    PlatformIO project for the ESP32-S3 camera
ros2_ws/
  src/robot_control/    ROS 2 nodes (serial bridge, camera bridge, teleop, mapping)
  src/robot_bringup/     launch files
  host_control/          operator-side helper scripts
  robot_start.sh         one-shot launcher (rock64 / pc roles)
docs/                ARCHITECTURE, QUICKSTART, HARDWARE_SAFETY
```

## Troubleshooting: motors hum but don't move

This means commands are reaching the Arduino (RX/TX blink) but the motors aren't
turning. Work down this list:

1. **Battery switch ON** — USB only powers the Arduino logic; the motor rail needs the
   battery pack.
2. **Charge the battery** — DC motors pull a large stall-current spike; a sagging pack
   collapses under load.
3. **Min-PWM** — confirm firmware `MIN_MOVE_PWM` (~80) is flashed; raise toward 95 if a
   full-stick command still only buzzes.
4. **Motor power wiring** — verify the battery feeds the shield's motor (VM/VIN) rail.

See [`docs/HARDWARE_SAFETY.md`](docs/HARDWARE_SAFETY.md) for power budget, data-only
USB cabling, common-ground, and motor-noise suppression details.
