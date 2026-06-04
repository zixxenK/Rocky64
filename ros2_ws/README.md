# Rock64 ROS 2 Workspace

This workspace is the active starting point for the ROS 2 migration of the
Rock64 robot.

The first ROS 2 milestone is intentionally narrow:

- the Rock64 runs only hardware-facing ROS 2 nodes
- the local PC publishes keyboard teleop over Wi-Fi
- the old ROS1 stack remains available as a fallback during bringup

## Current ROS 2 runtime

The hardware-facing ROS 2 package is [robot_control](src/robot_control).
Preferred runtime entrypoints now live in [robot_bringup](src/robot_bringup).
Future model and Gazebo assets now have a dedicated home in
[robot_description](src/robot_description).

It currently provides:

- `arduino_serial_bridge` for Arduino motor control over USB serial
- `esp32_camera_bridge` for the ESP32-CAM MJPEG stream
- `rock64_hardware.launch.py` for the default Rock64 hardware bringup
- `keyboard_teleop.launch.py` for local-PC keyboard control over ROS 2 DDS
- `keyboard_servo_teleop.launch.py` for local-PC `WASD` drive plus `Q/E` servo topics
- `ps5_teleop.launch.py` for local-PC DualSense control over ROS 2 DDS
- `robot_session.launch.py` for one-command hardware plus selectable teleop bringup
- `robot_control_launch.py` as a compatibility alias to the same hardware bringup
- `config/rock64_hardware.example.yaml` as the example parameter baseline

> Note: The PS5 controller must be plugged into the PC/WSL machine where `ps5_teleop.launch.py` is launched. The Rock64 runs the hardware-facing nodes, while the PC runs the controller input. Both machines must share the same `ROS_DOMAIN_ID` (for example `0`) and be on the same LAN.

The preferred launch package is:

- `robot_bringup/launch/rock64_bringup.launch.py`
- `robot_bringup/launch/keyboard_teleop.launch.py`
- `robot_bringup/launch/keyboard_servo_teleop.launch.py`
- `robot_bringup/launch/ps5_teleop.launch.py`
- `robot_bringup/launch/robot_session.launch.py`

The default hardware launch still does not start the operator teleop nodes. That
keeps serial and camera ownership in a single place while letting the PC choose
keyboard or PS5 control independently.

## Fresh-start preflight

Before launching ROS 2 nodes, run the host preflight helper to confirm the
current network, serial, and environment assumptions.

On the Rock64:

```bash
cd ~/Rock64\ Robot/ros2_ws
python3 host_control/bringup_preflight.py \
  --role rock64 \
  --network-mode station \
  --expected-ssid TELUS4424 \
  --camera-ip <esp32-dhcp-ip>
```

On the local PC:

```bash
cd ~/Rock64\ Robot/ros2_ws
python3 host_control/bringup_preflight.py \
  --role pc \
  --network-mode station \
  --expected-ssid TELUS4424 \
  --camera-ip <esp32-dhcp-ip> \
  --robot-host <rock64-lan-ip>
```

If the camera falls back to AP mode, use `--network-mode ap` and the default
camera IP `192.168.4.1`.

## Serial contract

The current ROS 2 bridge is aligned to the active PlatformIO motor firmware in
[firmware/mcu-motors/src/main.cpp](../firmware/mcu-motors/src/main.cpp).

- Default baud rate: `115200`
- Motor command format: `<motor_id,direction,speed>`
- Servo command format: `<SERVO,position>`
- Servo position range: `0` to `180`
- Motor mapping:
  - `1` = right motor
  - `2` = left motor
  - `direction` = `F`, `B`, or `S`

If the flashed Arduino firmware does not match that contract, verify the board
state before relying on the ROS 2 bridge.

## Install dependencies

From [ros2_ws](.):

```bash
python3 -m pip install -r requirements.txt
```

If you are using WSL Ubuntu 20.04, make sure the system Python pyserial package is installed too:

```bash
sudo apt update
sudo apt install python3-pyserial
```

On the Rock64, make sure the user can access the Arduino serial port:

```bash
sudo usermod -a -G dialout $USER
```

Log out and back in after changing group membership.

For keyboard teleop on the local PC, install the standard ROS 2 package:

```bash
sudo apt install ros-foxy-teleop-twist-keyboard
```

This workspace targets ROS 2 Foxy on Ubuntu 20.04.

## Build the package

```bash
cd ~/Rock64\ Robot/ros2_ws
./build_ros2_foxy.sh
```

If your shell has an older ROS1 or catkin overlay active, run the cleanup helper first on the Rock64:

```bash
cd ~/Rock64\ Robot/ros2_ws
./fix_bashrc_ros_overlay.sh
```

Then start a clean, isolated shell and rebuild. If stale ROS environment variables are still inherited when you open a new shell, use:

```bash
cd ~/Rock64\ Robot/ros2_ws
env -i HOME="$HOME" TERM="$TERM" PATH="/usr/bin:/bin" bash --noprofile --norc
source /opt/ros/foxy/setup.bash
source install/setup.bash
./build_ros2_foxy.sh
```

The helper script scans `~/.bashrc`, `~/.bash_profile`, and `~/.profile` for old ROS1/Noetic or catkin workspace sourcing lines and comments them out.

> Note: If `fix_bashrc_ros_overlay.sh` is not present on the Rock64, copy it there or update the Rock64 repository before running it.

## Run the Rock64 hardware stack

On the Rock64:

```bash
cd ~/Rock64\ Robot/ros2_ws
source ./source_ros2_foxy_ws.sh
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
ros2 launch robot_bringup rock64_bringup.launch.py \
  robot_namespace:=rock64_1 \
  serial_port:=/dev/ttyACM0 \
  baud_rate:=115200 \
  camera_url:=http://192.168.4.1/stream
```

If you prefer a guided script that resets mixed ROS env vars and validates the
workspace before launching, use:

```bash
cd ~/Rock64\ Robot/ros2_ws
bash ./rock64_hardware_start.sh ~/Rock64\ Robot/ros2_ws http://192.168.0.152/stream /dev/ttyACM0 rock64_1
```

To start hardware bringup plus a selectable operator mode in one command, use `robot_session.launch.py`:

```bash
ros2 launch robot_bringup robot_session.launch.py \
  robot_namespace:=rock64_1 \
  serial_port:=/dev/ttyACM0 \
  baud_rate:=115200 \
  camera_url:=http://192.168.4.1/stream \
  teleop_mode:=keyboard_servo
```

Available `teleop_mode` values are:

- `keyboard` - standard `teleop_twist_keyboard` drive-only control
- `keyboard_servo` - keyboard drive plus `Q/E` camera servo control
- `ps5` - PS5 DualSense drive and servo control

Compatibility launches in `robot_control` still work if you need the old path:

```bash
ros2 launch robot_control robot_control_launch.py
```

## Run one-command session bringup

If you want a single launch entry that starts hardware plus a selected teleop
mode, use:

```bash
cd ~/Rock64\ Robot/ros2_ws
source ./source_ros2_foxy_ws.sh
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
ros2 launch robot_bringup robot_session.launch.py \
  robot_namespace:=rock64_1 \
  camera_url:=http://192.168.0.152/stream \
  teleop_mode:=keyboard_servo
```

Supported `teleop_mode` values are `keyboard`, `keyboard_servo`, and `ps5`.
If the Rock64 is already running the hardware nodes, use
`include_hardware:=false` to start only the teleop side from another machine.

## Run operator-only teleop from a separate PC

If you want to keep the hardware drivers on the Rock64 and run only the
operator interface from your PC, use the new operator-only launch wrapper:

```bash
cd ~/Rock64\ Robot/ros2_ws
source ./source_ros2_foxy_ws.sh
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
ros2 launch robot_bringup operator_session.launch.py \
  robot_namespace:=rock64_1 \
  teleop_mode:=keyboard_servo
```

Equivalent helper script from the PC/WSL operator host:

```bash
cd /mnt/c/Desktop/Rock64\ Robot/ros2_ws
bash ./pc_operator_start.sh /mnt/c/Desktop/Rock64\ Robot/ros2_ws ps5 rock64_1
```

This starts only the teleop side and leaves the hardware bridge to run on the
physical Rock64. It is the recommended setup for a two-machine operator/robot
deployment.

## Known-good PS5 startup

Use these exact commands for the stable two-machine flow.

On the Rock64:

```bash
cd ~/Rock64\ Robot/ros2_ws
./build_ros2_foxy.sh
source ./source_ros2_foxy_ws.sh
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
ros2 launch robot_bringup rock64_bringup.launch.py \
  robot_namespace:=rock64_1 \
  serial_port:=/dev/ttyACM0 \
  baud_rate:=115200 \
  camera_url:=http://192.168.0.152/stream
```

On the Windows PC WSL shell after attaching the DualSense to `Ubuntu-20.04` with `usbipd`:

```bash
cd /mnt/c/Desktop/Rock64\ Robot/ros2_ws
./build_ros2_foxy.sh
source ./source_ros2_foxy_ws.sh
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
ros2 launch robot_bringup operator_session.launch.py \
  robot_namespace:=rock64_1 \
  teleop_mode:=ps5
```

Quick health check from either machine:

```bash
ros2 topic info /rock64_1/cmd_vel
```

Expected steady state for PS5 teleop is one publisher and at least one subscriber. If subscriber count is zero, the Rock64 hardware bridge is not running or not on the same ROS domain.

### Published and subscribed topics

With the default namespace, the Rock64 hardware launch uses:

- `/rock64_1/cmd_vel`
- `/rock64_1/camera_servo`
- `/rock64_1/robot_telemetry`
- `/rock64_1/camera/image_raw`

## Run keyboard teleop from the local PC

On the PC connected to the same network:

```bash
source /opt/ros/<distro>/setup.bash
cd ~/Rock64\ Robot/ros2_ws
source install/setup.bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
ros2 launch robot_bringup keyboard_teleop.launch.py \
  robot_namespace:=rock64_1
```

This keeps the operator input on the PC while the Rock64 owns the hardware.

## One-command fresh start (recommended)

To avoid environment drift and package discovery regressions, use the bootstrap
script [fresh_start.sh](fresh_start.sh). It performs a clean ROS env reset,
builds in merged-install mode, sources the overlay safely, verifies package
resolution, and runs role preflight checks.

Rock64 host:

```bash
cd ~/rock64_ros2_ws
./fresh_start.sh --role rock64 --workspace ~/rock64_ros2_ws --camera-ip 192.168.0.152
```

PC/WSL operator host:

```bash
cd /mnt/c/Desktop/Rock64\ Robot/ros2_ws
./fresh_start.sh --role pc --workspace /mnt/c/Desktop/Rock64\ Robot/ros2_ws --camera-ip 192.168.0.152 --robot-host <rock64-lan-ip>
```

When it completes successfully, it prints the next exact `ros2 launch` command
to run for that host role.

## Canonical PC to Rock64 sync (single method)

Use [sync_ros2_ws_to_rock64.ps1](sync_ros2_ws_to_rock64.ps1) from Windows PowerShell
as the only supported sync method from PC workspace to Rock64.

```powershell
cd "C:\Desktop\Rock64 Robot\ros2_ws"
.\sync_ros2_ws_to_rock64.ps1 -HostName rock64 -UserName rock64 -TargetDir ~/rock64_ros2_ws
```

If DNS host resolution is unreliable, use the Rock64 IP directly:

```powershell
.\sync_ros2_ws_to_rock64.ps1 -HostName 192.168.1.81 -UserName rock64 -TargetDir ~/rock64_ros2_ws
```

Dry-run preview:

```powershell
.\sync_ros2_ws_to_rock64.ps1 -HostName rock64 -UserName rock64 -TargetDir ~/rock64_ros2_ws -WhatIf
```

This script syncs `src/`, `host_control/`, and core startup/build scripts, then
marks shell entrypoints executable on Rock64.

If you prefer to run the underlying tool directly:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args \
  -r cmd_vel:=/rock64_1/cmd_vel
```

## Run keyboard teleop with camera-servo keys from the local PC

If you want ROS-side `Q/E` camera-servo publishing in addition to `WASD` drive,
use the pygame-based operator node:

```bash
source /opt/ros/<distro>/setup.bash
cd ~/Rock64\ Robot/ros2_ws
source install/setup.bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
ros2 launch robot_bringup keyboard_servo_teleop.launch.py \
  robot_namespace:=rock64_1
```

Focus the pygame window and use `W`, `A`, `S`, `D` for drive, `Q` and `E` for
camera servo target changes, and `Esc` to quit.

## Run PS5 teleop from the local PC

The PS5 controller must be connected to the PC or WSL instance where this launch is run. The Rock64 stays on the hardware side, and both machines must use the same `ROS_DOMAIN_ID` and be on the same LAN.

The PS5 launch now publishes on the robot namespace instead of the root topics:

```bash
source /opt/ros/<distro>/setup.bash
cd ~/Rock64\ Robot/ros2_ws
source install/setup.bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
ros2 run robot_control ps5_ros_bridge -- --list-controllers

ros2 launch robot_bringup ps5_teleop.launch.py \
  robot_namespace:=rock64_1 \
  joystick_index:=0 \
  controller_name:='' \
  leftx_axis:=0 \
  lefty_axis:=1 \
  rightx_axis:=2 \
  l2_axis:=4 \
  r2_axis:=5
```

If you need to target a different controller index, override
`joystick_index:=1` or set `controller_name:=<device-name>`.

### One-command startup from PC/WSL

If your PS5 DualSense is plugged into the PC/WSL machine, this single Windows command will start the teleop launch using ROS 2 Foxy and the installed workspace overlay:

```powershell
wsl.exe -d Ubuntu-20.04 -- /bin/bash -lc "cd '/mnt/c/Desktop/Rock64 Robot/ros2_ws' && . source_ros2_foxy_ws.sh && export ROS_DOMAIN_ID=0 && export ROS_LOCALHOST_ONLY=0 && ros2 launch robot_bringup ps5_teleop.launch.py robot_namespace:=rock64_1 joystick_index:=0 controller_name:='' leftx_axis:=0 lefty_axis:=1 rightx_axis:=2 l2_axis:=4 r2_axis:=5"
```

Before you run that command, verify WSL has ROS Foxy installed and the workspace path is accessible:

```powershell
wsl.exe -d Ubuntu-20.04 -- /bin/bash -lc "command -v ros2 >/dev/null && echo ROS2 OK || echo 'ROS2 missing in WSL'; ls '/mnt/c/Desktop/Rock64 Robot/ros2_ws' >/dev/null && echo WORKSPACE OK || echo 'Workspace path missing in WSL'"
```

This setup requires ROS Foxy to be installed inside the WSL distro and available at `/opt/ros/foxy/setup.bash`. If ROS is not installed in WSL, install ROS Foxy there or run the PS5 teleop launch from a Linux host that already has ROS.

If your WSL distro mounts Windows drives differently, replace `/mnt/c/...` with the mount path your distro actually uses.

## Quick validation

Before using keyboard teleop, validate the hardware path with a direct publish:

```bash
ros2 topic pub /rock64_1/cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.2}, angular: {z: 0.0}}' --once
```

Check serial output from the Arduino bridge:

```bash
ros2 topic echo /rock64_1/robot_telemetry
```

Check the camera stream topic exists:

```bash
ros2 topic list | grep rock64_1
```

Check that teleop servo messages are reaching ROS:

```bash
ros2 topic echo /rock64_1/camera_servo
```

## Camera notes

- AP mode default stream URL: `http://192.168.4.1/stream`
- Station mode: replace the URL with the DHCP address assigned by your router
- The camera bridge still supports JPEG fallback if MJPEG reads fail

## Legacy paths

- The ROS1 stack in [ros1_ws](../ros1_ws) remains the fallback path while ROS 2
  bringup is validated.
- `robot_control_node` is no longer part of the default ROS 2 launch path.
- PS5 support now has a dedicated operator launch, but it is still separate from
  the default hardware bringup.

## Current servo limitation

The active PlatformIO motor firmware in
[firmware/mcu-motors/src/main.cpp](../firmware/mcu-motors/src/main.cpp) now
implements the `<SERVO,position>` packet and attaches a servo on the configured
motor-shield servo pin. The current build defaults that pin to `3` in
[firmware/mcu-motors/platformio.ini](../firmware/mcu-motors/platformio.ini),
which matches the actual Uno + SmartCar shield servo header used by this
robot. If your servo is wired to a different shield connector, change
`-DCAMERA_SERVO_PIN=3` and rebuild before flashing.

## Next implementation targets

1. Run the new preflight workflow on real hardware and capture the confirmed LAN IPs.
2. Expand parameter/config coverage for hardware and network defaults.
3. Populate `robot_description` with URDF/xacro and Gazebo-facing assets.