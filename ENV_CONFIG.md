# Environment Configuration Guide

This document outlines the environment variables and sensitive credentials used in the Rock64 Robot project.

## Systemd Auto-Startup Services

The Rock64 Robot project includes systemd services for automated startup on both the Rock64 robot and PC operator machines. This enables hands-free operation where the robot automatically starts when powered on and the PC operator station automatically launches teleop control.

### Systemd Architecture

**Rock64 Robot Service (`rock64-robot.service`)**
- Starts automatically on boot
- Waits for network connectivity (configurable timeout)
- Waits for hardware detection (Arduino serial, camera network)
- Launches ROS2 hardware bridge nodes
- Optionally starts local teleop if controller detected
- Comprehensive error handling and fallback logic

**PC Operator Service (`rock64-operator.service`)**
- Starts automatically on boot
- Waits for network connectivity
- Prioritizes PS5 controller detection with keyboard fallback
- Launches teleop node and connects to Rock64 robot
- Handles controller disconnection gracefully

### Installation

Install systemd services using the deployment script:

```bash
# Install both Rock64 and PC services (default)
cd deployment
sudo ./rock64_setup.sh

# Install only Rock64 service
sudo ./rock64_setup.sh --rock64-only

# Install only PC service
sudo ./rock64_setup.sh --pc-only

# Skip systemd installation
sudo ./rock64_setup.sh --no-systemd
```

### Systemd Configuration

All service configuration is externalized to `/etc/rock64-robot/systemd_config.conf`. Edit this file to customize behavior without touching service files.

#### Configuration Parameters

```bash
# Network Configuration
ROCK64_IP=192.168.1.159              # Robot IP address
ROBOT_HOST=192.168.1.159             # Robot host for PC connection
DISCOVERY_SERVER=192.168.1.159:11811 # ROS2 discovery server
ROS_DOMAIN_ID=0                      # ROS2 domain ID
EXPECTED_SSID=TELUS4424              # Expected WiFi network

# Hardware Configuration
SERIAL_PORT=auto                     # auto, /dev/ttyUSB0, /dev/ttyACM0
BAUD_RATE=115200                     # Serial baud rate
CAMERA_IP_STATION=192.168.1.153      # Camera IP in station mode
CAMERA_IP_AP=192.168.4.1            # Camera IP in AP mode
CAMERA_PORT=80                       # Camera HTTP port
NETWORK_MODE=auto                    # auto, station, ap

# ROS2 Workspace Configuration
WORKSPACE_PATH=/home/rocky64/Rock64\ Robot/ros2_ws
ROS_DISTRO=foxy                      # ROS2 distribution
SKIP_BUILD=true                      # Skip colcon build on startup

# Hardware Detection Timeouts (seconds)
NETWORK_WAIT_TIMEOUT=60              # Max time to wait for network
HARDWARE_DETECTION_TIMEOUT=30        # Max time to wait for Arduino
CAMERA_DETECTION_TIMEOUT=30          # Max time to wait for camera
SERIAL_RECONNECT_DELAY=5             # Delay between serial reconnection attempts

# Service Configuration
ROBOT_NAMESPACE=rock64_1
SERVICE_USER=rocky64
SERVICE_GROUP=dialout

# Logging Configuration
LOG_LEVEL=INFO                       # DEBUG, INFO, WARN, ERROR
LOG_TO_SYSLOG=true
LOG_FILE=/var/log/rock64-robot.log

# Fallback Configuration
ALLOW_START_WITHOUT_ARDUINO=false    # Start ROS2 even if Arduino not detected
ALLOW_START_WITHOUT_CAMERA=false      # Start ROS2 even if camera not detected
FALLBACK_TO_KEYBOARD=true             # Fall back to keyboard if PS5 not detected on PC

# PC Operator Configuration
PC_TELEOP_MODE=ps5                   # ps5, keyboard, keyboard_servo
JOYSTICK_INDEX=0
CONTROLLER_NAME=DualSense

# Advanced Configuration
RESTART_ON_FAILURE=true
RESTART_DELAY_SEC=10
MAX_RESTART_COUNT=5
```

### Service Management Commands

```bash
# Rock64 Robot Service
sudo systemctl start rock64-robot.service      # Start service
sudo systemctl stop rock64-robot.service       # Stop service
sudo systemctl restart rock64-robot.service    # Restart service
sudo systemctl status rock64-robot.service     # Check status
sudo systemctl enable rock64-robot.service     # Enable auto-start on boot
sudo systemctl disable rock64-robot.service    # Disable auto-start

# PC Operator Service
sudo systemctl start rock64-operator.service    # Start service
sudo systemctl stop rock64-operator.service     # Stop service
sudo systemctl restart rock64-operator.service  # Restart service
sudo systemctl status rock64-operator.service    # Check status
sudo systemctl enable rock64-operator.service    # Enable auto-start on boot
sudo systemctl disable rock64-operator.service   # Disable auto-start
```

### Viewing Logs

```bash
# View Rock64 service logs in real-time
sudo journalctl -u rock64-robot.service -f

# View PC operator service logs in real-time
sudo journalctl -u rock64-operator.service -f

# View recent logs
sudo journalctl -u rock64-robot.service -n 50
sudo journalctl -u rock64-operator.service -n 50

# View logs since boot
sudo journalctl -u rock64-robot.service -b
sudo journalctl -u rock64-operator.service -b

# View log file (if configured)
sudo tail -f /var/log/rock64-robot.log
sudo tail -f /var/log/rock64-operator.log
```

### Startup Flow

**Rock64 Robot Startup Sequence:**
1. System boot → systemd launches `rock64-robot.service`
2. Service loads configuration from `/etc/rock64-robot/systemd_config.conf`
3. Sets up user permissions (dialout group for serial access)
4. Waits for network connectivity (up to 60s default)
5. Detects network mode (station/AP) based on WiFi availability
6. Waits for Arduino serial connection (up to 30s default)
7. Waits for camera network reachability (up to 30s default)
8. Sources ROS2 environment and workspace
9. Launches hardware bridge nodes (serial_robot_bridge, esp32_camera_bridge)
10. Detects local controller and optionally starts teleop
11. Ready for remote control from PC

**PC Operator Startup Sequence:**
1. System boot → systemd launches `rock64-operator.service`
2. Service loads configuration from `/etc/rock64-robot/systemd_config.conf`
3. Waits for network connectivity (up to 60s default)
4. Waits for Rock64 robot connectivity (up to 30s default)
5. Sources ROS2 environment and workspace
6. **PS5 Controller Detection (Priority):**
   - Uses multiple detection methods (evdev-list, udevadm, /proc/bus/input/devices, lsusb, direct joystick access)
   - Verifies controller accessibility
   - If PS5 detected → uses PS5 teleop
   - If PS5 not detected and FALLBACK_TO_KEYBOARD=true → uses keyboard teleop
7. Launches teleop node and connects to Rock64 robot
8. Ready for robot control

### Hardware Detection Details

**Arduino Serial Detection (Rock64):**
- Priority: `/dev/ttyUSB0` → `/dev/ttyACM0` → any `/dev/ttyUSB*` → any `/dev/ttyACM*`
- Verification: Attempts to open serial port at configured baud rate
- Timeout: 30 seconds default (configurable)
- Fallback: Can start without Arduino if `ALLOW_START_WITHOUT_ARDUINO=true`

**Camera Detection (Rock64):**
- Network mode detection: Checks for expected WiFi SSID
- Station mode: Pings `CAMERA_IP_STATION` (default: 192.168.1.153)
- AP mode: Pings `CAMERA_IP_AP` (default: 192.168.4.1)
- Verification: Attempts to fetch MJPEG stream from camera
- Timeout: 30 seconds default (configurable)
- Fallback: Can start without camera if `ALLOW_START_WITHOUT_CAMERA=true`

**PS5 Controller Detection (PC):**
- Method 1: `evdev-list` command (most reliable)
- Method 2: `/dev/input/event*` devices with udevadm
- Method 3: `/proc/bus/input/devices` parsing
- Method 4: `lsusb` USB device enumeration
- Method 5: Direct joystick device access test
- Verification: Attempts to read controller capabilities via evdev Python library
- Timeout: 30 seconds default (configurable)
- Fallback: Keyboard teleop if `FALLBACK_TO_KEYBOARD=true`

### Troubleshooting Systemd Services

**Service fails to start:**
```bash
# Check service status
sudo systemctl status rock64-robot.service
sudo systemctl status rock64-operator.service

# View detailed logs
sudo journalctl -u rock64-robot.service -n 100 --no-pager
sudo journalctl -u rock64-operator.service -n 100 --no-pager
```

**Hardware not detected:**
- Check configuration timeouts in `/etc/rock64-robot/systemd_config.conf`
- Verify physical connections (Arduino USB, camera network)
- Check user permissions: `groups $USER` should include `dialout` and `input`
- Manually test hardware: `ls /dev/ttyUSB*`, `ping <camera_ip>`, `evdev-list`

**Network issues:**
- Verify network connectivity: `ping <ROBOT_HOST>`
- Check ROS2 discovery server: `nc -z <DISCOVERY_SERVER_IP> <DISCOVERY_SERVER_PORT>`
- Verify ROS_DOMAIN_ID matches on both machines
- Check firewall settings on Rock64

**PS5 controller not detected on PC:**
- Verify controller is connected via USB
- Test controller detection: `evdev-list`, `lsusb | grep -i sony`
- Check user permissions: `groups $USER` should include `input`
- Verify evdev is installed: `python3 -c "import evdev; print(evdev.__version__)"`

**Service won't start after reboot:**
- Check if service is enabled: `sudo systemctl is-enabled rock64-robot.service`
- Check service status: `sudo systemctl status rock64-robot.service`
- View boot logs: `sudo journalctl -b -u rock64-robot.service`
- Verify network is ready before service starts: `systemctl is-active network-online.target`

### Manual Startup (Fallback)

If systemd services fail, you can manually start the robot using the original startup script:

```bash
# Rock64 robot side
cd ros2_ws
./robot_start.sh --role rock64

# PC operator side
cd ros2_ws
./robot_start.sh --role pc --teleop-mode ps5
```

## Environment Variables

## Security Important Notes

- **NEVER commit actual credentials to git**
- Use environment variables or separate configuration files for sensitive data
- SSH keys should be stored in `~/.ssh/` rather than hardcoded
- WiFi passwords should be stored in secure configuration

## Environment Variables

### WiFi Credentials
```bash
WIFI_PASSWORD=your_wifi_password_here
```
- Password for the TELUS4424 network
- Used by ESP32 firmware in station mode
- Should be set in your shell environment or .bashrc

### ESP32 Camera Configuration
```bash
ESP32_AP_PASSWORD=robot2026      # Access point mode password
ESP32_STA_PASSWORD=camncarm2021  # Station mode password
```
- Currently hardcoded in `firmware/esp32-vision/src/main.cpp`
- TODO: Move to secure configuration for production

### ROS 2 Configuration
```bash
ROS_DOMAIN_ID=0
ROS_DISCOVERY_SERVER=192.168.1.159:11811
ROS_LOCALHOST_ONLY=0
```
- Set automatically by `robot_start.sh`
- Can be overridden via command-line arguments

### Network Configuration
```bash
ROCK64_IP=192.168.1.159           # Robot (Rock64) static IP
CAMERA_IP_STATION=192.168.1.153  # Camera IP in station mode
CAMERA_IP_AP=192.168.4.1          # Camera IP in AP mode (fallback)
EXPECTED_SSID=TELUS4424          # Expected WiFi network
```
- Used by robot_start.sh for auto-detection
- Camera IP is automatically selected based on network mode

### Serial Configuration
```bash
SERIAL_PORT=/dev/ttyUSB0          # Preferred serial port
BAUD_RATE=115200                  # Serial communication speed
```
- Auto-detected by robot_start.sh
- Falls back to /dev/ttyACM0 if /dev/ttyUSB0 not available

## Setting Up Your Environment

### Option 1: Temporary (Current Session Only)
```bash
export WIFI_PASSWORD="your_password"
export ROS_DOMAIN_ID=0
export ROS_DISCOVERY_SERVER="192.168.1.159:11811"
```

### Option 2: Persistent (Add to .bashrc)
Add these lines to your `~/.bashrc`:
```bash
# Rock64 Robot Configuration
export WIFI_PASSWORD="your_password"
export ROS_DOMAIN_ID=0
export ROS_DISCOVERY_SERVER="192.168.1.159:11811"
```

Then reload your shell:
```bash
source ~/.bashrc
```

### Option 3: Using robot_start.sh
The `robot_start.sh` script automatically sets ROS environment variables:
```bash
./robot_start.sh --role rock64
```

You can override defaults:
```bash
./robot_start.sh --role rock64 --camera-ip 192.168.1.100 --serial-port /dev/ttyUSB0
```

## Configuration Files

### Main Configuration Files
- `ros2_ws/robot_start.sh` - Main startup script with auto-detection
- `ros2_ws/src/robot_control/config/rock64_hardware.yaml` - ROS2 hardware parameters
- `firmware/esp32-vision/src/main.cpp` - ESP32 firmware with WiFi credentials

### Current Configuration Summary

| Parameter | Value | Location |
|-----------|-------|----------|
| Rock64 IP | 192.168.1.159 | robot_start.sh default |
| Camera IP (Station) | 192.168.1.153 | robot_start.sh auto-detect |
| Camera IP (AP Mode) | 192.168.4.1 | robot_start.sh fallback |
| Expected SSID | TELUS4424 | robot_start.sh default |
| ROS_DOMAIN_ID | 0 | robot_start.sh default |
| Discovery Server | 192.168.1.159:11811 | robot_start.sh default |
| Serial Port | /dev/ttyUSB0 (auto-detect) | robot_start.sh & YAML |
| Baud Rate | 115200 | robot_start.sh & YAML |

## TODO: Security Improvements

1. Move ESP32 WiFi credentials to separate config file
2. Create secret management system for production deployments
3. Add .env file support for Python scripts
4. Implement secure credential storage for ESP32 firmware
5. Add SSH key management documentation

## Troubleshooting

### WiFi Connection Issues
- Verify SSID matches: `iwlist scan | grep TELUS4424`
- Check WiFi password in ESP32 firmware
- Test with manual connection: `nmcli dev wifi connect TELUS4424 password "your_password"`

### Serial Port Issues
- Check available ports: `ls -la /dev/ttyUSB* /dev/ttyACM*`
- Verify permissions: `sudo chmod 666 /dev/ttyUSB0`
- Test serial connection: `screen /dev/ttyUSB0 115200`

### ROS 2 Discovery Issues
- Verify environment variables: `echo $ROS_DISCOVERY_SERVER`
- Test connectivity: `ping 192.168.1.159`
- Check firewall settings on Rock64
