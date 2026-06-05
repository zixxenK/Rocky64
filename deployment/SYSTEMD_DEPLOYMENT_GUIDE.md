# Systemd Services Deployment Guide

This guide provides step-by-step instructions for deploying and testing the Rock64 Robot systemd services on both the Rock64 robot and PC operator machines.

## Prerequisites

### Hardware Requirements
- **Rock64 Robot Board**: Single-board computer running Ubuntu/Linux
- **Arduino**: Connected via USB serial for motor control
- **ESP32 Camera**: Network-connected camera module
- **PS5 DualSense Controller**: Connected to PC via USB
- **Network**: Both machines on same network with connectivity

### Software Requirements
- Ubuntu 20.04 or later (or compatible Linux distribution)
- ROS2 Foxy installed
- Python 3 with pip
- Systemd (included with most Linux distributions)
- User with sudo privileges

## Installation

### Step 1: Transfer Files to Target Machines

Copy the deployment directory to both Rock64 and PC machines:

```bash
# On development machine, transfer to Rock64
scp -r "Rock64 Robot" rocky64@192.168.1.159:/home/rocky64/

# Transfer to PC machine
scp -r "Rock64 Robot" user@pc-hostname:/home/user/
```

### Step 2: Install Rock64 Robot Service

On the Rock64 robot machine:

```bash
cd /home/rocky64/Rock64 Robot/deployment

# Run installation script
sudo ./rock64_setup.sh --rock64-only

# Or install both services if this is also an operator machine
sudo ./rock64_setup.sh
```

The installation script will:
- Install Python dependencies (pyserial, evdev, opencv)
- Add user to dialout and input groups
- Install systemd configuration file
- Copy and enable systemd service
- Set appropriate permissions

### Step 3: Install PC Operator Service

On the PC operator machine:

```bash
cd /home/user/Rock64 Robot/deployment

# Run installation script
sudo ./rock64_setup.sh --pc-only
```

### Step 4: Configure Services

Edit the configuration file on both machines:

```bash
sudo nano /etc/rock64-robot/systemd_config.conf
```

**Rock64 Configuration (minimal changes required):**
```bash
# Network Configuration
ROCK64_IP=192.168.1.159              # Your Rock64 IP
ROBOT_HOST=192.168.1.159
DISCOVERY_SERVER=192.168.1.159:11811
ROS_DOMAIN_ID=0
EXPECTED_SSID=TELUS4424              # Your WiFi network

# Hardware Configuration
SERIAL_PORT=auto                     # Let auto-detection work
BAUD_RATE=115200
CAMERA_IP_STATION=192.168.1.153      # Your camera IP
CAMERA_IP_AP=192.168.4.1
NETWORK_MODE=auto

# Workspace Configuration
WORKSPACE_PATH=/home/rocky64/Rock64\ Robot/ros2_ws
ROS_DISTRO=foxy
SKIP_BUILD=true                      # Set to false if workspace needs building
```

**PC Configuration:**
```bash
# Network Configuration
ROBOT_HOST=192.168.1.159             # Rock64 IP address
DISCOVERY_SERVER=192.168.1.159:11811
ROS_DOMAIN_ID=0

# PC Operator Configuration
PC_TELEOP_MODE=ps5                   # PS5 priority mode
FALLBACK_TO_KEYBOARD=true            # Fallback to keyboard if PS5 not detected
JOYSTICK_INDEX=0
CONTROLLER_NAME=DualSense

# Workspace Configuration
WORKSPACE_PATH=/home/user/Rock64\ Robot/ros2_ws
ROS_DISTRO=foxy
SKIP_BUILD=true
```

### Step 5: Verify Installation

Run the verification script on both machines:

```bash
cd /home/rocky64/Rock64 Robot/deployment
sudo ./verify_systemd_install.sh
```

The verification script will check:
- Configuration file existence and permissions
- Service file installation
- Script executability
- User permissions (dialout, input groups)
- Network connectivity
- Hardware detection (Arduino, camera, PS5 controller)
- ROS2 installation
- Workspace build status

Fix any reported issues before proceeding.

## Testing

### Manual Testing (Recommended First)

Before enabling auto-start, test the services manually:

#### Test Rock64 Robot Service

```bash
# Start the service manually
sudo systemctl start rock64-robot.service

# Check status
sudo systemctl status rock64-robot.service

# View logs in real-time
sudo journalctl -u rock64-robot.service -f
```

**Expected behavior:**
1. Service waits for network connectivity
2. Detects network mode (station/AP)
3. Waits for Arduino serial connection
4. Waits for camera network availability
5. Sources ROS2 environment
6. Launches hardware bridge nodes
7. Service stays running with "active (running)" status

**Common issues:**
- If Arduino not detected: Check USB connection, user permissions
- If camera not detected: Check camera IP, network connectivity
- If ROS2 fails: Check workspace build, environment sourcing

#### Test PC Operator Service

```bash
# Ensure PS5 controller is connected via USB
# Start the service manually
sudo systemctl start rock64-operator.service

# Check status
sudo systemctl status rock64-operator.service

# View logs in real-time
sudo journalctl -u rock64-operator.service -f
```

**Expected behavior:**
1. Service waits for network connectivity
2. Waits for Rock64 robot connectivity
3. Detects PS5 controller using multiple methods
4. Verifies controller accessibility
5. Sources ROS2 environment
6. Launches teleop node
7. Service stays running with "active (running)" status

**Common issues:**
- If PS5 not detected: Check USB connection, evdev installation
- If can't reach robot: Check network, ROS_DOMAIN_ID matching
- If teleop fails: Check joystick permissions, ROS2 topics

### Test Control Flow

With both services running:

1. **Verify hardware bridge is running:**
   ```bash
   # On Rock64
   ros2 topic list
   # Should see: /rock64_1/cmd_vel, /rock64_1/camera_servo, /rock64_1/camera/image_raw
   ```

2. **Verify teleop is publishing:**
   ```bash
   # On PC
   ros2 topic echo /rock64_1/cmd_vel
   # Should see Twist messages when using PS5 controller
   ```

3. **Verify motor control:**
   - Move PS5 controller sticks
   - Arduino should receive commands and motors should respond
   - Check Arduino serial monitor if available

4. **Verify camera stream:**
   ```bash
   # On Rock64 or PC
   ros2 topic hz /rock64_1/camera/image_raw
   # Should report camera publish rate (~10 Hz)
   ```

### Enable Auto-Start on Boot

Once manual testing is successful:

```bash
# On Rock64
sudo systemctl enable rock64-robot.service

# On PC
sudo systemctl enable rock64-operator.service
```

### Test Boot Sequence

1. Reboot both machines:
   ```bash
   sudo reboot
   ```

2. After reboot, check service status:
   ```bash
   # On Rock64
   sudo systemctl status rock64-robot.service
   
   # On PC
   sudo systemctl status rock64-operator.service
   ```

3. Verify services are active and robot is controllable.

## Troubleshooting

### Service Won't Start

**Check service status:**
```bash
sudo systemctl status rock64-robot.service
sudo systemctl status rock64-operator.service
```

**View detailed logs:**
```bash
sudo journalctl -u rock64-robot.service -n 100 --no-pager
sudo journalctl -u rock64-operator.service -n 100 --no-pager
```

**Common fixes:**
- Workspace not built: `cd ros2_ws && colcon build`
- User permissions: `sudo usermod -a -G dialout $USER`, logout/login
- Missing dependencies: `sudo apt install python3-evdev`
- Network timeout: Increase `NETWORK_WAIT_TIMEOUT` in config

### Hardware Not Detected

**Arduino not detected:**
```bash
# Check serial devices
ls -la /dev/ttyUSB* /dev/ttyACM*

# Test serial access
sudo screen /dev/ttyUSB0 115200

# Check permissions
groups $USER  # Should include dialout
```

**Camera not detected:**
```bash
# Ping camera
ping 192.168.1.153

# Test camera stream
curl http://192.168.1.153/stream

# Check network mode
iwlist scan | grep TELUS4424
```

**PS5 controller not detected:**
```bash
# Check USB connection
lsusb | grep -i sony

# Check input devices
ls -la /dev/input/

# Test evdev detection
evdev-list

# Check permissions
groups $USER  # Should include input
```

### Network Issues

**Can't reach robot from PC:**
```bash
# Test connectivity
ping 192.168.1.159

# Check ROS2 discovery
nc -z 192.168.1.159 11811

# Verify ROS_DOMAIN_ID matches on both machines
echo $ROS_DOMAIN_ID
```

**ROS2 DDS discovery failing:**
```bash
# Check firewall on Rock64
sudo ufw status

# Allow ROS2 ports if needed
sudo ufw allow 11811/udp
sudo ufw allow 7400/udp
```

### Service Restarts Frequently

**Check restart count:**
```bash
sudo systemctl status rock64-robot.service | grep "StartLimitInterval"
```

**Adjust restart policy in service file:**
```bash
sudo nano /etc/systemd/system/rock64-robot.service
# Modify: RestartSec, StartLimitInterval, StartLimitBurst
sudo systemctl daemon-reload
```

**Increase timeout for slow hardware:**
```bash
sudo nano /etc/rock64-robot/systemd_config.conf
# Increase: NETWORK_WAIT_TIMEOUT, HARDWARE_DETECTION_TIMEOUT
```

## Maintenance

### Updating Services

When updating the robot software:

```bash
# Stop services
sudo systemctl stop rock64-robot.service
sudo systemctl stop rock64-operator.service

# Update workspace
cd ~/Rock64 Robot/ros2_ws
git pull
colcon build

# Restart services
sudo systemctl start rock64-robot.service
sudo systemctl start rock64-operator.service
```

### Monitoring Services

**Create monitoring script:**
```bash
#!/bin/bash
# monitor_services.sh

while true; do
  echo "=== $(date) ==="
  echo "Rock64 Service:"
  systemctl is-active rock64-robot.service
  echo "PC Service:"
  systemctl is-active rock64-operator.service
  echo ""
  sleep 60
done
```

**Check service health periodically:**
```bash
# Add to crontab for automated monitoring
crontab -e
# Add: */5 * * * * /usr/local/bin/check_robot_services.sh
```

### Log Rotation

Configure log rotation for service logs:

```bash
sudo nano /etc/logrotate.d/rock64-robot

# Add:
/var/log/rock64-robot.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 644 rocky64 rocky64
}

/var/log/rock64-operator.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 644 user user
}
```

## Uninstallation

To remove systemd services:

```bash
# Stop and disable services
sudo systemctl stop rock64-robot.service
sudo systemctl stop rock64-operator.service
sudo systemctl disable rock64-robot.service
sudo systemctl disable rock64-operator.service

# Remove service files
sudo rm /etc/systemd/system/rock64-robot.service
sudo rm /etc/systemd/system/rock64-operator.service

# Remove configuration
sudo rm -rf /etc/rock64-robot

# Reload systemd
sudo systemctl daemon-reload

# Remove log files (optional)
sudo rm /var/log/rock64-robot.log
sudo rm /var/log/rock64-operator.log
```

## Performance Tuning

### Reduce Startup Time

If services start too slowly:

```bash
# Reduce timeout values in config
sudo nano /etc/rock64-robot/systemd_config.conf
NETWORK_WAIT_TIMEOUT=30              # Reduce from 60
HARDWARE_DETECTION_TIMEOUT=15        # Reduce from 30
CAMERA_DETECTION_TIMEOUT=15          # Reduce from 30
```

### Optimize Resource Usage

If services use too much CPU/memory:

```bash
# Add resource limits to service files
sudo nano /etc/systemd/system/rock64-robot.service
# Add under [Service]:
MemoryLimit=512M
CPUQuota=50%
```

## Security Considerations

### Network Security

- Use firewalls to restrict access to ROS2 ports
- Consider using VPN for remote operation
- Change default passwords in ESP32 firmware

### User Permissions

- Service runs as non-root user (rocky64 or specified user)
- Serial and input devices require group membership
- Consider creating dedicated robot user

### Configuration Security

- Configuration file contains network IPs and credentials
- Set appropriate file permissions:
  ```bash
  sudo chmod 640 /etc/rock64-robot/systemd_config.conf
  sudo chown root:rocky64 /etc/rock64-robot/systemd_config.conf
  ```

## Support and Documentation

- Main documentation: See `ENV_CONFIG.md`
- Service configuration: `/etc/rock64-robot/systemd_config.conf`
- Service logs: `sudo journalctl -u rock64-robot.service -f`
- Verification script: `deployment/verify_systemd_install.sh`
- Installation script: `deployment/rock64_setup.sh`

## Summary

The systemd services provide:
- ✅ Automated startup on boot
- ✅ Network connectivity waiting
- ✅ Hardware detection with timeout
- ✅ PS5 controller priority detection
- ✅ Graceful fallback handling
- ✅ Comprehensive error logging
- ✅ Configuration externalization
- ✅ User permission management
- ✅ Service restart on failure

With these services deployed, your Rock64 robot will automatically start when powered on and be ready for control via the PS5 controller connected to your PC.
