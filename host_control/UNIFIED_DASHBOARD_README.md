# Unified Robot Dashboard - Quick Start Guide

## Overview

The Unified Robot Dashboard integrates all robot control components into a single web-based interface with automatic boot orchestration.

## Components

- **unified_dashboard.py** - Main Flask web server with integrated services
- **unified_index.html** - Web UI with video stream, manual control, agent status
- **dashboard_boot.py** - Boot orchestrator for starting/stopping all subsystems
- **dashboard_config.json** - Configuration file for dashboard settings
- **rock64-dashboard.service** - Systemd service for auto-boot on Rock64

## Features

- **Single Web Interface** - All controls in one dashboard
- **Video Streaming** - ESP32/USB/ROS2 camera support
- **Manual Control** - Virtual joystick, keyboard, PS5 controller
- **Agent Integration** - Start/stop/restart AI agent from web UI
- **System Boot** - One-click boot of all subsystems
- **Real-time Telemetry** - WebSocket updates for sensor data
- **Cross-Platform** - Works on Windows, Linux, and Rock64

## Installation

### On Rock64 (Auto-boot)

1. Copy files to Rock64:
   ```bash
   # From Windows PC
   python ros2_ws/sync_ros2_ws_to_rock64.ps1
   ```

2. Install systemd service (run ON ROCK64):
   ```bash
   cd ~/ros2_ws/deployment
   sudo ./install_dashboard_service.sh
   ```

3. Dashboard will auto-start on boot at `http://<rock64-ip>:5000`

### Manual Start (Any Platform)

1. Start with boot orchestrator:
   ```bash
   cd host_control
   python dashboard_boot.py --start
   ```

2. Or start dashboard directly:
   ```bash
   python unified_dashboard.py --port 5000 --boot-all
   ```

## Usage

### Web Interface

Open browser to `http://<host-ip>:5000`

- **System Status Bar** - Shows ROS2, SSH, Serial, Camera, Agent status
- **Camera Stream** - Live video feed
- **Manual Control** - Virtual joystick or keyboard (WASD + QE)
- **Mode Switching** - Manual/Agent/E-Stop
- **Agent Controls** - Start/Stop/Restart AI agent
- **Telemetry** - Ultrasonic, motor speeds, servo position
- **Configuration** - Motor, safety, servo settings
- **System Boot** - Boot/Shutdown all services

### Keyboard Controls

- `W` / `S` - Forward / Backward
- `A` / `D` - Turn Left / Right
- `Q` / `E` - Servo Left / Right
- `Space` - Stop

### Boot Orchestrator Commands

```bash
# Start all services
python dashboard_boot.py --start

# Stop all services
python dashboard_boot.py --stop

# Restart all services
python dashboard_boot.py --restart

# Show service status
python dashboard_boot.py --status

# Run as daemon with monitoring
python dashboard_boot.py --daemon
```

### Systemd Service Commands (Rock64)

```bash
# Start service
sudo systemctl start rock64-dashboard

# Stop service
sudo systemctl stop rock64-dashboard

# Restart service
sudo systemctl restart rock64-dashboard

# Check status
sudo systemctl status rock64-dashboard

# View logs
sudo journalctl -u rock64-dashboard -f
```

## Configuration

Edit `dashboard_config.json` to customize:

```json
{
  "platform": "auto",
  "ros2_enabled": true,
  "agent_enabled": true,
  "camera_enabled": true,
  "dashboard_enabled": true,
  "ros2_workspace": "/home/rock64/ros2_ws",
  "ros2_launch_file": "rock64_bringup.launch.py",
  "dashboard_host": "0.0.0.0",
  "dashboard_port": 5000,
  "serial_port": "/dev/ttyUSB0",
  "baud_rate": 115200,
  "rock64_host": "192.168.1.159",
  "camera_source": "esp32",
  "camera_url": "http://192.168.1.153/stream",
  "auto_boot": true
}
```

## Architecture

### Boot Sequence

1. Serial connection to Arduino
2. SSH connection to Rock64 (if needed)
3. ROS2 launch (Linux only)
4. Camera initialization
5. Agent controller start
6. Web dashboard start

### Service Dependencies

- **Dashboard** depends on Serial, SSH (optional), Camera (optional)
- **Agent** depends on SSH (for motor commands), Camera (optional)
- **ROS2** (Linux only) provides hardware bridges

### Cross-Platform Behavior

- **Windows**: Dashboard + Agent + Camera (no ROS2)
- **Linux/Rock64**: Dashboard + Agent + Camera + ROS2
- **Fallback**: Graceful degradation if services unavailable

## Troubleshooting

### Dashboard won't start

1. Check Python dependencies:
   ```bash
   pip3 install flask flask-socketio pyserial opencv-python
   ```

2. Check serial port permissions:
   ```bash
   sudo usermod -a -G dialout $USER
   ```

3. Check camera stream:
   - ESP32: Ensure camera is accessible at configured URL
   - USB: Check camera index with `ls /dev/video*`

### Agent won't start

1. Check SSH connection to Rock64:
   ```bash
   ssh -i ~/.ssh/rock64_sync rock64@192.168.1.159
   ```

2. Check agent script exists:
   ```bash
   ls host_control/agent_controller.py
   ```

### ROS2 won't start (Linux)

1. Check ROS2 workspace:
   ```bash
   ls ~/ros2_ws/install/setup.bash
   ```

2. Source ROS2 environment:
   ```bash
   source /opt/ros/foxy/setup.bash
   ```

### Service fails to start (systemd)

1. Check service logs:
   ```bash
   sudo journalctl -u rock64-dashboard -n 100
   ```

2. Check service status:
   ```bash
   sudo systemctl status rock64-dashboard
   ```

3. Manually test dashboard:
   ```bash
   cd ~/ros2_ws/host_control
   python3 unified_dashboard.py --port 5000
   ```

## Migration from Legacy Components

### From control_center.py

The unified dashboard replaces `control_center.py`. To migrate:

1. Configuration files are compatible (`robot_config.json`, `agent_config.json`)
2. API endpoints are the same
3. WebSocket events are the same
4. New features: video stream, agent integration, system boot

### From agent_controller.py

The agent can still run standalone, or be managed by the dashboard:

- **Standalone**: `python agent_controller.py`
- **Managed**: Start/stop from web UI or boot orchestrator

### From windows_control.py

Windows control remains separate for console-based control:

- Use `windows_control.py` for direct SSH control without web UI
- Use unified dashboard for web-based control with all features

## API Endpoints

### Configuration
- `GET /api/config` - Get robot configuration
- `POST /api/config` - Update robot configuration
- `GET /api/agent/config` - Get agent configuration
- `POST /api/agent/config` - Update agent configuration

### Mode
- `GET /api/agent/mode` - Get current mode
- `POST /api/agent/mode` - Set mode

### System
- `GET /api/system/status` - Get system status
- `POST /api/system/boot` - Boot all services
- `POST /api/system/shutdown` - Shutdown all services

### Agent
- `POST /api/agent/start` - Start agent
- `POST /api/agent/stop` - Stop agent
- `POST /api/agent/restart` - Restart agent

### Control
- `POST /api/control/motor` - Send motor command
- `POST /api/control/servo` - Send servo command

### Emergency
- `POST /api/emergency/stop` - Emergency stop
- `POST /api/emergency/reset` - Reset from emergency

### Camera
- `GET /api/camera/stream` - MJPEG camera stream

## WebSocket Events

- `telemetry_update` - Real-time telemetry data
- `mode_update` - Mode change notification
- `system_status` - System status updates
- `emergency_stop` - Emergency stop notification

## Development

### Adding New Features

1. Add API endpoint in `unified_dashboard.py`
2. Add WebSocket event handler if needed
3. Update UI in `unified_index.html`
4. Update configuration schema if needed

### Testing

```bash
# Test dashboard without booting services
python unified_dashboard.py --port 5000

# Test boot orchestrator
python dashboard_boot.py --start
python dashboard_boot.py --status
python dashboard_boot.py --stop

# Test systemd service (Rock64)
sudo systemctl start rock64-dashboard
sudo systemctl status rock64-dashboard
```

## Support

For issues or questions:
1. Check logs: `journalctl -u rock64-dashboard -f`
2. Check configuration: `dashboard_config.json`
3. Check service status: `systemctl status rock64-dashboard`
