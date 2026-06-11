# Unified Dashboard Architecture Plan

## Current State Analysis

### Existing Components

1. **control_center.py** (Flask Web Dashboard)
   - Configuration management (motor, safety, servo)
   - Agent configuration API
   - Telemetry display via WebSocket
   - Serial connection management
   - Mode switching (MANUAL/AGENT/E-STOP)
   - REST API endpoints

2. **agent_controller.py** (Standalone AI Agent)
   - Computer vision (OpenCV)
   - Obstacle detection
   - Navigation logic
   - SSH connection to Rock64
   - Mode state management
   - Runs as separate process

3. **windows_control.py** (Windows Control)
   - PS5 DualSense controller
   - WASD keyboard control
   - SSH pipe to Rock64
   - No ROS2 required

4. **index.html** (Web UI)
   - Mode control buttons
   - Telemetry display
   - Configuration forms
   - Serial connection UI

### Integration Points

- **Mode State**: Shared via `agent_mode.txt` file
- **Configuration**: Shared via JSON files (`robot_config.json`, `agent_config.json`)
- **Serial Communication**: Both use platform_utils for port detection
- **SSH Connection**: Both connect to Rock64 for motor commands

## Unified Dashboard Architecture

### 1. Backend Integration (unified_dashboard.py)

#### Component: Agent Service Integration
- Run agent_controller as background thread/service within Flask app
- Expose agent status via WebSocket
- Provide agent start/stop/restart controls
- Stream agent vision frames to web UI

#### Component: Camera Stream Integration
- Add ESP32 camera stream endpoint
- Add ROS2 camera topic subscription (when on Linux)
- Provide MJPEG stream endpoint for web display
- Support multiple camera sources (ESP32, USB, ROS2)

#### Component: Manual Control Interface
- Add virtual joystick controls in web UI
- Add keyboard control via WebSocket
- Integrate PS5 controller detection (Windows)
- Send motor commands through same channel as agent

#### Component: System Status Monitoring
- ROS2 node status (when on Linux)
- SSH connection status to Rock64
- Serial port connection status
- Camera stream status
- Agent process status

#### Component: Boot Orchestrator
- Start/stop ROS2 launch (Linux only)
- Start/stop agent controller
- Start/stop camera stream
- Manage process lifecycle
- Provide boot sequence status

### 2. Frontend UI (unified_index.html)

#### Layout Sections

1. **Header**
   - System status indicators (ROS2, SSH, Serial, Camera, Agent)
   - Current mode display (MANUAL/AGENT/E-STOP)
   - Emergency stop button (prominent)

2. **Video Stream Panel**
   - Live camera feed (ESP32/USB/ROS2)
   - Agent vision overlay (when in AGENT mode)
   - Obstacle detection visualization

3. **Control Panel**
   - Mode switcher (Manual/Agent/E-Stop)
   - Manual controls:
     - Virtual joystick (touch/mouse)
     - Keyboard control indicator
     - PS5 controller status (Windows)
   - Agent controls:
     - Start/Stop/Restart agent
     - Agent status display
     - Learning metrics

4. **Telemetry Panel**
   - Ultrasonic distance
   - Motor speeds
   - Servo position
   - Obstacle detection status
   - Agent navigation state

5. **Configuration Panel** (collapsible)
   - Motor configuration
   - Safety configuration
   - Servo configuration
   - Agent configuration
   - Serial connection settings

6. **System Panel** (collapsible)
   - Boot controls (Start All/Stop All)
   - ROS2 launch controls
   - Service status indicators
   - Log viewer

### 3. Boot Orchestrator (dashboard_boot.py)

#### Responsibilities
- Platform detection (Windows/Linux/Rock64)
- Start services in correct order:
  1. Serial connection
  2. SSH connection (if needed)
  3. ROS2 launch (Linux only)
  4. Agent controller
  5. Camera stream
  6. Web dashboard
- Monitor service health
- Auto-restart failed services
- Provide boot status via WebSocket

#### Cross-Platform Behavior
- **Windows**: Start web dashboard + agent controller + camera stream
- **Linux/Rock64**: Start ROS2 launch + web dashboard + agent controller
- **Fallback**: Graceful degradation if services unavailable

### 4. Systemd Service (rock64-dashboard.service)

#### Configuration
- Auto-start on Rock64 boot
- Depends on network
- Restart on failure
- Log to systemd journal
- Managed by boot orchestrator

## Implementation Phases

### Phase 1: Backend Integration
1. Create `unified_dashboard.py` extending `control_center.py`
2. Integrate agent_controller as background thread
3. Add camera stream endpoint
4. Add system status monitoring
5. Add boot orchestrator functions

### Phase 2: Frontend UI
1. Create `unified_index.html` extending `index.html`
2. Add video stream display
3. Add virtual joystick controls
4. Add agent status panel
5. Add system status panel
6. Add boot controls

### Phase 3: Boot Orchestrator
1. Create `dashboard_boot.py`
2. Implement platform detection
3. Implement service startup sequence
4. Add health monitoring
5. Add auto-restart logic

### Phase 4: Systemd Integration
1. Create `rock64-dashboard.service`
2. Add to systemd configuration
3. Test auto-boot on Rock64
4. Test service recovery

## API Extensions

### New REST Endpoints
- `POST /api/system/boot` - Start all services
- `POST /api/system/shutdown` - Stop all services
- `POST /api/system/restart` - Restart all services
- `GET /api/system/status` - Get system status
- `POST /api/agent/start` - Start agent
- `POST /api/agent/stop` - Stop agent
- `POST /api/agent/restart` - Restart agent
- `GET /api/camera/stream` - MJPEG stream endpoint

### New WebSocket Events
- `system_status` - System status updates
- `agent_status` - Agent status updates
- `camera_frame` - Camera frame (if using MJPEG over WebSocket)
- `boot_progress` - Boot sequence progress

## Configuration Files

### dashboard_config.json
```json
{
  "platform": "auto",
  "ros2_enabled": true,
  "agent_enabled": true,
  "camera_source": "esp32",
  "camera_url": "http://192.168.1.153/stream",
  "manual_control": "virtual_joystick",
  "auto_boot": true,
  "services": {
    "ros2_launch": {
      "enabled": true,
      "workspace": "/home/rock64/ros2_ws",
      "launch_file": "rock64_bringup.launch.py"
    },
    "agent_controller": {
      "enabled": true,
      "camera_index": 0
    },
    "camera_stream": {
      "enabled": true,
      "source": "esp32"
    }
  }
}
```

## File Structure

```
host_control/
├── unified_dashboard.py          # Main unified dashboard backend
├── unified_index.html            # Unified web UI
├── dashboard_boot.py             # Boot orchestrator
├── dashboard_config.json         # Dashboard configuration
├── agent_service.py              # Agent as service (extracted from agent_controller.py)
├── camera_stream.py              # Camera stream service
├── system_monitor.py            # System status monitor
├── control_center.py             # Legacy (keep for compatibility)
├── agent_controller.py           # Legacy (keep for standalone use)
├── windows_control.py           # Legacy (keep for Windows-only control)
└── templates/
    ├── index.html                # Legacy
    └── unified_index.html        # New unified UI
```

## Migration Strategy

1. Keep legacy files for backward compatibility
2. New unified dashboard is opt-in via `dashboard_boot.py`
3. Gradually migrate features from legacy to unified
4. Eventually deprecate legacy files after testing

## Testing Strategy

1. Unit tests for each service integration
2. Integration tests for boot sequence
3. Cross-platform testing (Windows, Linux, Rock64)
4. Load testing for WebSocket streams
5. Failover testing for service crashes
