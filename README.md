# Rock64 Robot

 Packages:     Ubuntu stable (resolute)
 Updates:      Kernel upgrade enabled and 7 packages available for upgrade
 Support:      for advanced users (rolling release)
 IPv4:        (LAN) 192.168.1.159 (WAN) 207.6.171.199
 IPv6:        (LAN) 2001:569:ba4d:3700:7b34:ffee:2105:f015 (WAN) 2001:569:ba4d:3700:fda2:2b24:1b54:ade1

ros 
Reviewing the repo structure and ROS workspace to tailor the ROS1 migration instructions.

Read [](file:///c%3A/Desktop/Rock64%20Robot/ros2_ws/README.md)

Read [](file:///c%3A/Desktop/Rock64%20Robot/ros2_ws)

## Rock64 Ubuntu Desktop + ROS 1 migration plan

You should move the Rock64 to a reproducible ROS 1 host architecture where:

- the Rock64 runs Ubuntu Desktop (or a lightweight Ubuntu-derived desktop),
- the Uno and ESP32 communicate through ROS topics,
- the host side is a `catkin` workspace with launch files and parameter files,
- microcontroller ports and camera URL are configured in one place.

---

## 1. Rock64 Ubuntu Desktop setup

### 1.1 Choose the right image
For Rock64, use Ubuntu 20.04 LTS arm64-based distro:

- recommended: `Armbian Focal` for Rock64
- optional: Ubuntu 20.04 Desktop if a Rock64 build exists
- if desktop performance is a concern, use `xubuntu-desktop` or `xfce4`

### 1.2 Flash the Rock64 storage
1. Download the image
2. Flash to SD or eMMC with balenaEtcher
3. Boot Rock64 with HDMI monitor / keyboard
4. Create a user and password

### 1.3 Initial Rock64 setup
Open a terminal and run:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y build-essential curl gnupg2 lsb-release \
  git python3 python3-pip python3-venv \
  cmake libpython3-dev
```

Add your user to serial groups:

```bash
sudo usermod -aG dialout $USER
sudo usermod -aG video $USER
```

Reboot:

```bash
sudo reboot
```

### 1.4 Install a desktop environment
If you want a full desktop on a Rock64, install a lightweight DE:

```bash
sudo apt install -y xfce4 xfce4-goodies
```

For a more standard Ubuntu Desktop:

```bash
sudo apt install -y ubuntu-desktop
```

---

## 2. ROS 1 installation on Rock64

### 2.1 Recommended ROS distribution
Use ROS Noetic on Ubuntu 20.04.

### 2.2 Install ROS Noetic packages
If `ros-noetic-ros-base` is available for arm64:

```bash
sudo sh -c 'echo "deb http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main" > /etc/apt/sources.list.d/ros1-latest.list'
sudo apt install -y curl gnupg2
curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | sudo apt-key add -
sudo apt update
sudo apt install -y ros-noetic-ros-base
```

Then initialize ROS environment:

```bash
source /opt/ros/noetic/setup.bash
echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc
```

### 2.3 Install ROS build tools and dependencies

```bash
sudo apt install -y python3-rosdep python3-rosinstall-generator \
  python3-vcstool python3-catkin-tools python3-rosinstall python3-wstool
sudo rosdep init
rosdep update
```

### 2.4 If apt packages are not available for arm64
Build from source:

```bash
mkdir -p ~/catkin_ws/src
cd ~/catkin_ws
rosinstall_generator ros_comm rosserial image_common --rosdistro noetic --deps --tar > noetic-ros_comm.rosinstall
vcs import src < noetic-ros_comm.rosinstall
rosdep install --from-paths src --ignore-src --rosdistro noetic -y
catkin_make
source devel/setup.bash
```

---

## 3. ROS architecture for the robot

### 3.1 ROS package layout
Create a `catkin_ws` with packages like:

- `robot_bringup`
- `robot_msgs`
- `arduino_serial_bridge`
- `esp32_camera_bridge`

### 3.2 Arduino / microcontroller communications
Use ROS topics instead of custom host scripts.

#### Uno side
- Use `rosserial_arduino`
- Publish:
  - `/motor_state`
  - `/heartbeat`
- Subscribe:
  - `/cmd_vel`
  - `/motor_control`

Host node:
- `rosrun rosserial_python serial_node.py /dev/ttyACM0` or `/dev/ttyUSB0`
- `rosparam set /serial_port /dev/ttyACM0`
- `rosparam set /baud 115200`

Example node launch:

```xml
<launch>
  <node name="arduino_serial" pkg="rosserial_python" type="serial_node.py">
    <param name="port" value="/dev/ttyACM0"/>
    <param name="baud" value="115200"/>
  </node>
</launch>
```

#### ESP32-CAM side
Use a ROS node that:
- connects to the ESP32-CAM AP or station IP,
- fetches MJPEG or single-image frames,
- converts them to `sensor_msgs/Image`,
- publishes `/camera/image_raw`.

Example topics:
- `/camera/image_raw`
- `/camera/camera_info`

A simple Python ROS node can use OpenCV:

```python
import rospy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2

bridge = CvBridge()
pub = rospy.Publisher('/camera/image_raw', Image, queue_size=1)
cap = cv2.VideoCapture('http://192.168.4.1/stream')

while not rospy.is_shutdown():
    ret, frame = cap.read()
    if ret:
        msg = bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        pub.publish(msg)
```

---

## 4. Reproducible setup with ROS launch files

### 4.1 Example `robot_bringup.launch`

```xml
<launch>
  <include file="$(find rosserial_python)/launch/serial_node.launch">
    <arg name="port" value="/dev/ttyACM0"/>
    <arg name="baud" value="115200"/>
  </include>

  <node pkg="esp32_camera_bridge" type="camera_bridge.py" name="esp32_camera_bridge" output="screen">
    <param name="camera_url" value="http://192.168.4.1/stream"/>
    <param name="camera_topic" value="/camera/image_raw"/>
  </node>
</launch>
```

### 4.2 Example `params.yaml`

```yaml
serial_port: /dev/ttyACM0
baudrate: 115200
camera_url: http://192.168.4.1/stream
camera_topic: /camera/image_raw
```

### 4.3 Standard ROS runtime
Then start the full system with:

```bash
source ~/catkin_ws/devel/setup.bash
roslaunch robot_bringup rock64_robot.launch
```

---

## 5. Microcontroller communications handled entirely by ROS

### 5.1 Arduino Uno
1. Connect Uno to Rock64 USB.
2. Use `rosserial_python` on Rock64.
3. Arduino sketch uses `ros.h`, `std_msgs`, `geometry_msgs` or custom messages.
4. Host and Uno exchange commands and heartbeat over ROS topics.

### 5.2 ESP32-CAM
1. Put the ESP32 in AP or STA mode.
2. Have Rock64 join the network or connect directly.
3. Use a ROS image bridge node to publish `/camera/image_raw`.
4. Use standard ROS tools like `rqt_image_view` or `rosbag` to inspect and record.

---

## 6. Recommended path for your repo

This repo now includes an active ROS1 Noetic workspace under `ros1_ws`. The existing `ros2_ws` folder is still a future ROS2 migration placeholder.

- build `ros1_ws` with `catkin_make`
- use `roslaunch robot_bringup rock64_robot.launch`
- the current packages are:
  - `ros1_ws/src/arduino_serial_bridge`
  - `ros1_ws/src/esp32_camera_bridge`
  - `ros1_ws/src/robot_bringup`

### Serial wiring for the Rock64 <-> Uno link

- Rock64 pin `9` → Uno GND (blue cable)
- Rock64 pin `12` → Uno pin `2` (brown cable)
- Rock64 pin `14` → Uno pin `4` (white cable)

> This wiring maps the Uno serial-style GPIO pair into the Rock64 header. Confirm TX/RX orientation before running the node.

---

## 7. Quick start summary

### Install Ubuntu / desktop
```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y xfce4
```

### Install ROS Noetic
```bash
sudo apt install -y ros-noetic-ros-base
source /opt/ros/noetic/setup.bash
```

### Create workspace
```bash
mkdir -p ~/ros1_ws/src
cd ~/ros1_ws
catkin_make
source devel/setup.bash
```

### Build the ROS1 robot packages
```bash
cd ~/ros1_ws
catkin_make
source devel/setup.bash
```

### Run the full robot stack
```bash
roslaunch robot_bringup rock64_robot.launch
```

---

## 8. What to do next

- Build the ROS1 packages in `ros1_ws`.
- Verify the Uno is connected using the exact pin wiring in section 6.
- Use `roslaunch robot_bringup rock64_robot.launch` to start the full stack.
- Keep the ESP32 and Uno communications defined as ROS topics and sensor messages.
- Use `roslaunch` and YAML configuration so setup is reproducible.

If you want, I can next generate a concrete ROS1 package structure for this repo and a `roslaunch`/`CMakeLists.txt` scaffold.



=============
This repository implements a distributed robotics platform built around a Pine64 Rock64 SBC, an Arduino Uno R3 motor controller, and an ESP32-CAM vision node.
rocky64@rock64:~$ sudo nmcli device wifi connect "TELUS4424" password "camncarm2021"
Error: 802-11-wireless-security.key-mgmt: property is missing.
rocky64@rock64:~$ sudo nmcli device wifi connect "TELUS4424" password "camncarm2021"
Error: 802-11-wireless-security.key-mgmt: property is missing.
rocky64@rock64:~$ ip addr show wlan0
nmcli connection show --active
Device "wlan0" does not exist.
NAME       UUID                                  TYPE      DEVICE          
TELUS4424  6e38de67-e918-47bc-afd2-e065afde70d6  wifi      wlxc89e4394f6c6 
lo         ad5601c9-75ab-499c-b834-85a0bf2976d3  loopback  lo              
rocky64@rock64:~$ ip addr show wlxc89e4394f6c6
4: wlxc89e4394f6c6: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000
    link/ether c8:9e:43:94:f6:c6 brd ff:ff:ff:ff:ff:ff
    inet 192.168.1.159/24 brd 192.168.1.255 scope global dynamic noprefixroute wlxc89e4394f6c6
       valid_lft 84452sec preferred_lft 84452sec
    inet6 2001:569:ba4d:3700:a56e:8395:3211:fc77/64 scope global temporary dynamic 
       valid_lft 21476sec preferred_lft 14276sec
    inet6 2001:569:ba4d:3700:7b34:ffee:2105:f015/64 scope global dynamic mngtmpaddr noprefixroute 
       valid_lft 21476sec preferred_lft 14276sec
    inet6 fe80::a13:f35d:510c:7baf/64 scope link noprefixroute 
       valid_lft forever preferred_lft forever

or simply:

```bash
sudo nmcli device wifi connect "TELUS4424" password "camncarm2021"
```

To connect to the ESP32-CAM AP, use:

```bash
sudo nmcli device wifi connect "ESP32-CAM-AP" password "robot2026"
```

## Project overview
- **Rock64 SBC**: high-level host, serial telemetry bridge, and vision stream ingestion.
- **Arduino Uno R3**: low-level real-time motor control with a motor shield.
- **ESP32-CAM**: wireless MJPEG video stream source.
- **Separated power rails**: motor power and logic power remain isolated with a common ground.

## Hardware in this repository
- Rockchip RK3328 Rock64 single-board computer
- Arduino Uno R3 with Elegoo L293D / TB6612FNG motor shield
- ESP32-CAM (OV2640) camera module
- 4× yellow DC gear motors for 4WD drive
- SG90 servo for sensor rotation
- HC-SR04 ultrasonic sensor for distance sensing
- DHT11 temperature/humidity sensor (optional)
- Logitech K400 wireless keyboard for console control
- MB102 breadboard power modules for regulated 5V/3.3V logic power

## Repository structure
- `README.md` — primary project overview and setup instructions.
- `docs/ARCHITECTURE.md` — consolidated architecture and integration reference.
- `setup` — architecture, hardware stack, power integration, and deployment guidance.
- `geminiresearchsuggestions` — detailed design notes and system-level planning.
- `deployment/` — Rock64 host setup script and deployment configuration.
- `firmware/mcu-motors/` — Arduino Uno motor controller firmware.
- `firmware/esp32-vision/` — ESP32-CAM MJPEG streaming firmware.
- `ros2_ws/` — host control Python stack and ROS 2 workspace placeholder.

## Firmware and host integration
- `firmware/mcu-motors/src/main.cpp` implements an asynchronous serial packet protocol and heartbeat-safe motor control.
- `firmware/esp32-vision/src/main.cpp` runs a Wi-Fi AP and serves an MJPEG stream at `/stream`.
- `ros2_ws/host_control/` contains the smoke-test Python host stack:
  - `serial_bridge.py` — sends motor commands to the Arduino.
  - `camera_stream.py` — reads the ESP32-CAM stream asynchronously.
  - `main.py` — validates serial and camera integration.

## Quick start
1. Flash the Arduino Uno firmware in `firmware/mcu-motors/src/main.cpp`.
2. Flash the ESP32-CAM firmware in `firmware/esp32-vision/src/main.cpp`.
3. Prepare the Rock64 host:
   - run `deployment/rock64_setup.sh`, or install `python3`, `python3-pip`, `python3-opencv`, `git`, and `pyserial` manually.
4. Run the host control smoke test from `ros2_ws/`:
   ```bash
   python3 host_control/main.py --serial-port /dev/ttyS1 --camera-ip 192.168.4.1
   ```
5. Confirm the ESP32-CAM stream and serial port are accessible.

## ESP32-CAM boot and Wi-Fi troubleshooting
- If `ESP32-CAM-AP` is not visible, open the serial monitor on the ESP32 board and reset it.
- If the serial monitor shows `ESP-ROM:esp32s3...`, the board is in flash/bootloader mode. Release `IO0` from GND and reset normally.
- If the ESP32 still does not create the AP, verify the board is using the correct S3 camera model and pin mapping in `firmware/esp32-vision/src/main.cpp`.

## Safety and runtime behavior
- The Arduino firmware enforces a **200 ms heartbeat timeout** and uses the AVR watchdog timer to stop motors safely when commands stop.
- The host should use a stable serial connection and keep the camera stream on a low-latency Wi-Fi network.
- Use separate power sources for motor drive and Rock64 logic, with one common ground.

## Deployment notes
- `deployment/rock64_setup.sh` installs required Linux packages and adds the user to the `dialout` group for serial access.
- The ESP32-CAM firmware creates an AP called `ESP32-CAM-AP` with password `robot2026`.
- Use `http://192.168.4.1/stream` as the default camera URL when the ESP32-CAM is in AP mode.

## Next steps
1. Verify the physical wiring, motor driver power, and common ground.
2. Test the serial bridge and emergency stop logic.
3. Connect the Rock64 to a 5GHz network or local access point for low-latency telemetry.
4. Extend the host stack into ROS 2 packages once hardware integration is stable.

For a deeper system-level architecture and the full hardware/software roadmap, see `geminiresearchsuggestions` and `setup`.


## Rock64 GPIO wiring (40-pin header)

| Physical pin | Voltage | Wire colour | Function |
|---|---|---|---|
| 2 | 5 V | Red | 5 V power rail to Arduino Vin |
| 6 | GND | Black | Ground — Rock64 logic GND |
| 9 | GND | Blue | Common ground — bridges motor-side GND to logic GND |
| 8 | 3.3 V | — | **UART2 TX** (GPIO14) — Rock64 transmits → Arduino digital pin 2 (SoftwareSerial RX) |
| 10 | 3.3 V | — | **UART2 RX** (GPIO15) — Rock64 receives ← Arduino digital pin 4 (SoftwareSerial TX) |

> **Important pin naming note:** physical pin numbers on the Rock64 header are not the same as internal GPIO labels.
> Physical pin 14 is a ground pin, while the internal GPIO14 serial TX signal lives on physical pin 8.
> Do not use physical pin 14 for UART data lines.
>
> **Arduino serial wiring:** the firmware uses `SoftwareSerial` on pins **2 (RX)** and **4 (TX)** at 9600 baud.
> This avoids using hardware pins 0/1 during USB programming and prevents upload conflicts.
>
> **Wiring confirmed:** This wiring is correct for the Rock64 ↔ Arduino SoftwareSerial crossover.
> Physical pin 8 goes to Arduino pin 2, and physical pin 10 goes to Arduino pin 4.
>
> **Ground note:** Any Rock64 ground pin such as physical pin 6, 9, or 14 may be used for the blue ground wire.
> Just do not use physical pin 14 for signal wiring.
>
> **Upload rule:** With this SoftwareSerial wiring, you can leave the brown/white RX-TX wires
> connected during Arduino USB uploads because they no longer share pins 0/1.
>
> **⚠ Voltage mismatch:** Arduino TX (pin 4) still outputs a 5 V signal;
> Rock64 RX (physical pin 10) is 3.3 V. Use a 1 kΩ / 2 kΩ voltage divider or logic-level shifter on that line.

## Rock64 network setup

```bash
# Bring up USB ethernet adapter
sudo ip link set enx606d3ca812b9 up
sudo wpa_supplicant -B -i enx606d3ca812b9 \
    -c /etc/wpa_supplicant/wpa_supplicant.conf -Dnl80211,wext
```

`/etc/wpa_supplicant/wpa_supplicant.conf` template:

```
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=CA

network={
    ssid="YOUR_SSID"
    psk="YOUR_PASSWORD"
    key_mgmt=WPA-PSK
}
```