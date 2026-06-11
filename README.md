# Rock64 Robot

A teleoperated 4WD robot built on an Elegoo Smart Car chassis with **dual-platform support**:
- **Windows**: Direct SSH control to Rock64 (no ROS2 required on Windows)
- **Linux/ROS2**: Full ROS2 Foxy architecture for advanced robotics

A PS5 DualSense (or keyboard) drives the robot; an ESP32-S3 streams video over WiFi.

> This README is an overview. For step-by-step run instructions see
> [`docs/QUICKSTART.md`](docs/QUICKSTART.md), for the system design see
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and for wiring/power safety see
> [`docs/HARDWARE_SAFETY.md`](docs/HARDWARE_SAFETY.md).

## Architecture at a glance

### Windows Host Control (Simplified)
```
Windows PC ──PS5/Keyboard @20Hz──► SSH ──► Rock64: /dev/ttyUSB0 @115200── Arduino Uno
                                              │                         └─ <id,dir,spd> → motors
ESP32-S3 ◄──MJPEG over WiFi── Rock64 (camera bridge)
```

### Linux/ROS2 (Full Robotics Stack)
```
Operator PC ──PS5 @20Hz──► cmd_vel (ROS 2 DDS, shared ROS_DOMAIN_ID)
                               │
        Rock64: arduino_serial_bridge ──USB /dev/ttyUSB0 @115200── Arduino Uno
                               │                                    └─ <id,dir,spd> → motors
        Rock64: esp32_camera_bridge ◄──MJPEG over WiFi── ESP32-S3 (camera only)
```

- **Windows path**: Direct SSH from Windows to Rock64 serial port. No ROS2 required on Windows.
- **Linux/ROS2 path**: Full ROS2 Foxy architecture with DDS for distributed control.
- **Motor control runs over the single USB serial link** between the Rock64 and the Arduino.
- **The ESP32-S3 is camera-only** (MJPEG stream). It does not relay motor commands.

## Components

### Windows Host Control
| Component | Where | Role |
|-----------|-------|------|
| `ps5_windows_bridge.py` | Windows PC | PS5 DualSense → SSH → Rock64 serial @ 20 Hz |
| `agent_controller.py` | Windows PC | AI autonomous navigation with computer vision |
| `control_center.py` | Windows PC | Flask web UI for configuration and telemetry |
| `windows_control.py` | Windows PC | Unified keyboard + controller input |

### Linux/ROS2
| Node | Where | Role |
|------|-------|------|
| `ps5_ros_bridge` | Operator PC | DualSense → `cmd_vel` Twist @ 20 Hz |
| `arduino_serial_bridge` | Rock64 | `cmd_vel` → `<id,dir,spd>` serial packets |
| `esp32_camera_bridge` | Rock64 | ESP32 MJPEG → `sensor_msgs/Image` |

### Firmware
| Component | Hardware | Role |
|-----------|----------|------|
| `mcu-motors/src/main.cpp` | Arduino Uno | Parse packets, drive H-bridge, 200 ms heartbeat |
| `esp32-vision/src/main.cpp` | ESP32-S3 | WiFi + MJPEG camera server |

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

### Windows (Recommended for simple teleop)

```powershell
# Install dependencies
python -m pip install -r requirements.txt

# PS5 controller bridge
.\robot_start.ps1 --script ps5 --host 192.168.1.159

# AI agent controller (autonomous navigation)
.\robot_start.ps1 --script agent --host 192.168.1.159

# Web control center
.\robot_start.ps1 --script control --port 5000

# Unified control (keyboard + controller, switch with Tab)
.\robot_start.ps1 --script unified --host 192.168.1.159
```

**Windows Prerequisites:**
- Python 3.8+ installed
- SSH key at `~/.ssh/rock64_sync` (or specify with `--ssh-key`)
- Rock64 reachable via SSH (test: `ssh -i ~/.ssh/rock64_sync rock64@192.168.1.159`)
- PS5 controller connected via USB (for controller modes)

### Linux/ROS2 (Full robotics stack)

```bash
# Rock64 (robot side)
cd ros2_ws
./robot_start.sh --role rock64 --serial-port /dev/ttyUSB0 --camera-ip 192.168.1.153

# Operator PC (PS5 teleop)
./robot_start.sh --role pc --robot-host 192.168.1.159 --teleop-mode ps5

# Operator PC on WSL / no display (headless keyboard — no window needed)
./robot_start.sh --role pc --robot-host 192.168.1.159 --teleop-mode keyboard_terminal
```

> On WSL the windowed `keyboard_servo` teleop can't open (no display). Use
> `--teleop-mode keyboard_terminal` to drive from the terminal, or set up a
> display — see [`docs/QUICKSTART.md`](docs/QUICKSTART.md#teleop-on-wsl--no-display).

Camera preview (no ROS needed): open `http://<esp32-ip>/stream` in a browser.

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for prerequisites, keyboard controls,
and DDS multicast troubleshooting.

## Repository layout

```
firmware/
  mcu-motors/      PlatformIO project for the Arduino Uno (src/main.cpp)
  esp32-vision/    PlatformIO project for the ESP32-S3 camera
host_control/     Windows host control scripts (SSH-based, no ROS2 required)
  ps5_windows_bridge.py    PS5 controller → SSH → Rock64
  agent_controller.py      AI autonomous navigation
  control_center.py        Flask web UI
  windows_control.py       Unified keyboard + controller
  platform_utils.py        Cross-platform utilities
ros2_ws/
  src/robot_control/    ROS 2 nodes (serial bridge, camera bridge, teleop, mapping)
  src/robot_bringup/     launch files
  robot_start.sh         Linux/ROS2 launcher (rock64 / pc roles)
docs/                ARCHITECTURE, QUICKSTART, HARDWARE_SAFETY
requirements.txt     Unified Python dependencies (platform-specific markers)
robot_start.ps1     Windows PowerShell launcher
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

## Platform-Specific Troubleshooting

### Windows SSH Connection Issues

If the Windows host control scripts fail to connect to Rock64:

1. **Test SSH manually**: `ssh -i ~/.ssh/rock64_sync rock64@192.168.1.159`
2. **Check network connectivity**: `ping 192.168.1.159`
3. **Verify SSH key path**: Ensure the key exists at the specified location
4. **Check Rock64 SSH service**: Ensure SSH is running on the Rock64
5. **Firewall**: Ensure Windows firewall allows SSH outbound connections

### Windows Serial Port Issues

The Windows scripts use SSH to access Rock64's serial port, so Windows serial ports
are not directly used. If you see serial port errors:

1. **Verify Rock64 serial device**: SSH into Rock64 and check `ls /dev/tty*`
2. **Check Arduino connection**: Ensure Arduino is connected to Rock64 via USB
3. **Serial port permissions**: On Rock64, ensure rock64 user can access `/dev/ttyUSB0`

### Linux/ROS2 DDS Discovery Issues

If ROS2 nodes can't discover each other:

1. **Check ROS_DOMAIN_ID**: Ensure both machines use the same domain ID (default: 0)
2. **Multicast blocked**: WiFi often blocks multicast - use unicast peer configuration
3. **Firewall**: Ensure ROS2 ports (DDS) are not blocked by firewall
4. **Network interface**: Ensure both machines are on the same network segment
