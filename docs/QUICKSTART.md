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

> **Running under WSL?** `keyboard_servo` opens a pygame **window**, which
> needs a display server. WSL has none by default, so the window shows up
> blank/frozen. Use `--teleop-mode keyboard_terminal` (below) for a
> no-display option, or set up a display — see
> [Teleop on WSL / no display](#teleop-on-wsl--no-display).

#### Headless keyboard teleop (no display — recommended for WSL)

```bash
./robot_start.sh --role pc \
    --robot-host 192.168.1.159 \
    --teleop-mode keyboard_terminal
```

This drives the robot straight from the terminal — **no window, no X
server**. Keep the terminal focused and use the same WASD/QE keys. It runs
`ros2 run robot_control keyboard_terminal_teleop`, which reads keystrokes
from stdin, so it must be run in an interactive terminal (not piped). The
camera stream is not shown here; open `http://<camera-ip>/stream` in a
browser to watch video.

### Option B — Windows (no ROS 2 installed)

Use the direct SSH bridge that pipes input straight to the Arduino serial
port, bypassing ROS entirely.

**Recommended — unified control (PS5 *or* WASD, switch with Tab):**

```powershell
python host_control/windows_control.py --host 192.168.1.159
```

It auto-detects a DualSense; press **Tab** any time to switch between the
controller and **WASD keyboard** (`W/S` drive, `A/D` turn, `Q/E` camera servo,
`Space` stop, `Esc` quit). Start in a specific mode with
`--source keyboard` or `--source controller`. Use `--dry-run` to print packets
without driving, and `--list-joysticks` to find your controller's index.

**PS5-only (original):**

```powershell
python host_control/ps5_windows_bridge.py --host 192.168.1.159
```

Both require `pygame` and `ssh` (Git for Windows ships with ssh); the keyboard
path uses the stdlib `msvcrt`, so no extra install is needed for WASD.

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

> **Can't reach the camera from your PC?** The ESP32 is on the robot's LAN.
> Your PC must be on the **same** WiFi/subnet (`192.168.1.x`, on `TELUS4424`,
> no VPN/Ethernet/guest network). Check with `ipconfig`, then
> `ping 192.168.1.153`. If the camera is up but only the Rock64 can reach it,
> use the LAN re-stream below.

### LAN re-stream (watch from any device — recommended)

Run a re-streamer **on the Rock64** so it holds the single ESP32 connection and
fans frames out to every device on the LAN (phones, laptops, tablets):

```bash
# on the Rock64
python3 ~/rock64_ros2_ws/host_control/lan_camera_restream.py --camera-ip 192.168.1.153
```

Then on any device on the same WiFi open `http://<rock64-ip>:8080/`
(`/stream`, `/snapshot.jpg`, and `/status` are also available). Or start it
automatically with the robot:

```bash
./robot_start.sh --stream-port 8080
```

### ROS 2 image viewer

```bash
ros2 run rqt_image_view rqt_image_view \
    --ros-args -r image:=/rock64_1/camera/image_raw
```

## Stable hostnames (mDNS) — stop chasing DHCP IPs

DHCP can hand the Rock64 and camera new IPs on any reboot, which breaks
hard-coded addresses. mDNS gives them stable `.local` names instead.

**Rock64 → `rock64.local`** (run once on the Rock64, no firmware needed):

```bash
./setup_mdns_rock64.sh        # installs + enables avahi-daemon
```

Then from any device on the WiFi: `ssh rock64@rock64.local`, and the LAN
re-stream at `http://rock64.local:8080/`. (Windows 10/11 and macOS resolve
`.local` out of the box; most Linux distros do too via nss-mdns.)

**Camera → `esp32-cam.local`** (requires re-flashing the ESP32): the firmware
advertises itself over mDNS, so once flashed you can use the name everywhere:

```bash
./robot_start.sh --camera-ip esp32-cam.local
python3 host_control/lan_camera_restream.py --upstream http://esp32-cam.local/stream
```

**No-code fallback:** if mDNS is flaky on your network, add **DHCP
reservations** in your router (pin the Rock64 and camera MACs to fixed IPs).
Then the existing IP-based commands keep working across reboots.

## DDS Discovery Troubleshooting

ROS 2 Foxy uses FastDDS with multicast discovery by default.  Many WiFi
routers drop multicast packets, preventing the two machines from finding
each other.

`robot_start.sh` now **auto-generates** a unicast peer profile at launch — no
manual XML editing. It writes `~/.ros/fastdds_unicast.generated.xml` containing
loopback, this machine's LAN IP, and the other side, then exports
`FASTRTPS_DEFAULT_PROFILES_FILE` to it.

- **PC side** already lists the robot (you pass `--robot-host <ip>`), which is
  enough for bidirectional discovery:

  ```bash
  ./robot_start.sh --role pc --robot-host 192.168.1.159 --teleop-mode keyboard_terminal
  ```

- **Rock64 side** can optionally add the PC for symmetry, plus any extra peers:

  ```bash
  ./robot_start.sh --pc-host 192.168.1.81            # add the operator PC
  ./robot_start.sh --peer 192.168.1.50 --peer 192.168.1.51   # extra machines
  ```

Hostnames are resolved to IPs automatically (e.g. `--robot-host rock64.local`).
The static `fastdds_unicast.xml` shipped in the package is kept only as a
fallback if generation fails.

## Teleop on WSL / no display

ROS 2 itself runs fine in WSL, but the GUI teleop (`keyboard_servo`, which
uses pygame) and the OpenCV `stream_viewer` window both need a **display
server**. WSL has none out of the box, so a GUI window appears blank or
frozen — this is the most common "I launched teleop but can't open the
window" symptom. Three ways to deal with it:

1. **Headless terminal teleop (recommended — zero setup).** Use
   `--teleop-mode keyboard_terminal`. It drives from the terminal with no
   window at all. See
   [Headless keyboard teleop](#headless-keyboard-teleop-no-display--recommended-for-wsl)
   above.

2. **WSLg (Windows 11).** WSL ships with built-in GUI support. Confirm it
   works:

   ```bash
   echo $DISPLAY        # should print something like :0
   ```

   If `$DISPLAY` is empty, update WSL from PowerShell and reopen your
   terminal:

   ```powershell
   wsl --update
   wsl --shutdown
   ```

3. **VcXsrv / X server (Windows 10).** Install
   [VcXsrv](https://sourceforge.net/projects/vcxsrv/), launch **XLaunch**
   with *"Disable access control"* checked, then in WSL:

   ```bash
   export DISPLAY=$(awk '/nameserver/{print $2}' /etc/resolv.conf):0
   export LIBGL_ALWAYS_INDIRECT=1
   ```

   Add those two lines to `~/.bashrc` to make them persistent.

Regardless of display, the camera stream is always viewable in a browser at
`http://<camera-ip>/stream` (no ROS or display required). When no display
is present, `stream_viewer` logs that it is running headless instead of
crashing.

## Keyboard controls (keyboard_servo / keyboard_terminal modes)

| Key | Action |
|-----|--------|
| W   | Forward |
| S   | Backward |
| A   | Turn left |
| D   | Turn right |
| Q   | Camera servo left |
| E   | Camera servo right |
| Space / K | Stop (terminal mode) |
| Esc | Quit |

Both modes share the same keys. `keyboard_servo` reads held keys from a
pygame window; `keyboard_terminal` reads them from the terminal (relying on
key auto-repeat plus a short hold timeout), so tap-and-hold to keep moving
and tap **Space**/**K** to stop immediately.

## PS5 DualSense controls

| Input | Action |
|-------|--------|
| Left stick Y | Forward / backward |
| Right stick X | Turn left / right |
| L2 | Slow mode |
| R2 | Boost mode |
| D-pad left/right | Camera servo |
