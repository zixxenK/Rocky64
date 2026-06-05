# Rock64 Robot — Two-Machine Quick Start

This guide covers launching the robot from **two machines**: the Rock64
(robot side) and your operator PC (teleop + video).

## Prerequisites

| Machine | Requirements |
|---------|-------------|
| Rock64  | Ubuntu 20.04, ROS 2 Foxy, `ros2_ws` synced and built |
| PC      | ROS 2 Foxy (Linux) or `ps5_windows_bridge.py` (Windows) |
| Network | Both on the same WiFi subnet (e.g. `192.168.1.x`) |

## 1. Launch the robot (Rock64)

SSH into the Rock64 and run:

```bash
cd ~/Rock64\ Robot/ros2_ws
./robot_start.sh --role rock64 \
    --serial-port /dev/ttyUSB0 \
    --camera-ip 192.168.1.153
```

This starts:
- `arduino_serial_bridge` — listens on `/rock64_1/cmd_vel` and
  `/rock64_1/camera_servo`, forwards motor/servo packets to the Arduino
  via serial.
- `esp32_camera_bridge` — connects to the ESP32 MJPEG stream and
  publishes frames to `/rock64_1/camera/image_raw`.

Wait for `All checks passed — launching (rock64)` before proceeding.

## 2. Launch the operator teleop (PC)

### Option A — ROS 2 on Linux

```bash
cd ~/ros2_ws   # or wherever you have the workspace
./robot_start.sh --role pc \
    --robot-host 192.168.1.159 \
    --teleop-mode keyboard_servo
```

Or for PS5 DualSense:

```bash
./robot_start.sh --role pc \
    --robot-host 192.168.1.159 \
    --teleop-mode ps5
```

### Option B — Windows (no ROS 2 installed)

Use the direct SSH bridge that pipes PS5 input straight to the Arduino
serial port, bypassing ROS entirely:

```powershell
python host_control/ps5_windows_bridge.py --host 192.168.1.159
```

This requires `pygame` and `ssh` (Git for Windows ships with ssh).

## 3. Verify connectivity

On the Rock64, check that topics are flowing:

```bash
# List active topics
ros2 topic list

# Should see:
#   /rock64_1/cmd_vel
#   /rock64_1/camera_servo
#   /rock64_1/camera/image_raw

# Watch cmd_vel (should show Twist messages when you push sticks)
ros2 topic echo /rock64_1/cmd_vel
```

If the PC's topics are not visible on the Rock64 (or vice versa), your
WiFi router is likely blocking DDS multicast. See [DDS Discovery
Troubleshooting](#dds-discovery-troubleshooting) below.

## 4. View the camera stream

### Quick browser check (no ROS needed)

Open in any browser: `http://192.168.1.153/stream`

### ROS 2 image viewer

```bash
ros2 run rqt_image_view rqt_image_view \
    --ros-args -r image:=/rock64_1/camera/image_raw
```

## DDS Discovery Troubleshooting

ROS 2 Foxy uses FastDDS with multicast discovery by default.  Many WiFi
routers drop multicast packets, preventing the two machines from finding
each other.

The workspace ships with `fastdds_unicast.xml` which configures unicast
peer discovery. `robot_start.sh` exports it automatically:

```
export FASTRTPS_DEFAULT_PROFILES_FILE=.../config/fastdds_unicast.xml
```

**You must edit the file** to list both machines' IPs:

```xml
<!-- Rock64 -->
<address>192.168.1.159</address>
<!-- Operator PC -->
<address>192.168.1.81</address>
```

Copy the same file to the PC and export the env var there too before
running the PC-side launch.

## Keyboard controls (keyboard_servo mode)

| Key | Action |
|-----|--------|
| W   | Forward |
| S   | Backward |
| A   | Turn left |
| D   | Turn right |
| Q   | Camera servo left |
| E   | Camera servo right |
| Esc | Quit |

## PS5 DualSense controls

| Input | Action |
|-------|--------|
| Left stick Y | Forward / backward |
| Right stick X | Turn left / right |
| L2 | Slow mode |
| R2 | Boost mode |
| D-pad left/right | Camera servo |
