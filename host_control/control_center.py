#!/usr/bin/env python3
"""
control_center.py — Web-based control center for robot configuration and agent control.

Features:
- REST API for configuration management
- WebSocket for real-time telemetry
- Configuration persistence (JSON)
- Agent command interface
- Emergency controls
- Learning dashboard

Usage:
  python host_control/control_center.py
  python host_control/control_center.py --port 5000
"""

import argparse
import json
import os
import sys
import threading
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit
import serial
import serial.tools.list_ports

# Import platform utilities for cross-platform compatibility
from platform_utils import get_default_serial_port


# --- CONFIGURATION ---
@dataclass
class MotorConfig:
    min_speed: int = 100
    max_speed: int = 180
    invert_direction: bool = False


@dataclass
class SafetyConfig:
    stop_distance: int = 10
    warning_distance: int = 30
    max_speed_limit: int = 180


@dataclass
class ServoConfig:
    scan_range: int = 90
    scan_speed: int = 20


@dataclass
class RobotConfig:
    motor1: MotorConfig = None
    motor2: MotorConfig = None
    safety: SafetyConfig = None
    servo: ServoConfig = None
    
    def __post_init__(self):
        if self.motor1 is None:
            self.motor1 = MotorConfig()
        if self.motor2 is None:
            self.motor2 = MotorConfig()
        if self.safety is None:
            self.safety = SafetyConfig()
        if self.servo is None:
            self.servo = ServoConfig()


@dataclass
class AgentConfig:
    forward_speed: int = 120
    turn_speed: int = 80
    cautious_speed: int = 60
    safe_distance: int = 50
    warning_distance: int = 100
    exploration_rate: float = 0.1
    learning_rate: float = 0.01


@dataclass
class TelemetryState:
    ultrasonic_distance: int = 100
    motor1_speed: int = 0
    motor2_speed: int = 0
    servo_position: int = 90
    mode: str = "MANUAL"
    obstacle_detected: bool = False
    obstacle_direction: str = "none"
    last_update: str = ""


# --- FLASK APP ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'robot-control-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- GLOBAL STATE ---
config_file = os.path.join(os.path.dirname(__file__), "robot_config.json")
agent_config_file = os.path.join(os.path.dirname(__file__), "agent_config.json")
mode_file = os.path.join(os.path.dirname(__file__), "agent_mode.txt")

robot_config = RobotConfig()
agent_config = AgentConfig()
telemetry = TelemetryState()
serial_connection: Optional[serial.Serial] = None


# --- CONFIGURATION MANAGEMENT ---
def load_robot_config() -> RobotConfig:
    """Load robot configuration from file."""
    global robot_config
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                data = json.load(f)
                robot_config = RobotConfig(
                    motor1=MotorConfig(**data.get('motor1', {})),
                    motor2=MotorConfig(**data.get('motor2', {})),
                    safety=SafetyConfig(**data.get('safety', {})),
                    servo=ServoConfig(**data.get('servo', {}))
                )
    except Exception as e:
        print(f"[control] Failed to load config: {e}")
    return robot_config


def save_robot_config() -> None:
    """Save robot configuration to file."""
    global robot_config
    try:
        with open(config_file, 'w') as f:
            json.dump(asdict(robot_config), f, indent=2)
        print(f"[control] Saved config to {config_file}")
    except Exception as e:
        print(f"[control] Failed to save config: {e}")


def load_agent_config() -> AgentConfig:
    """Load agent configuration from file."""
    global agent_config
    try:
        if os.path.exists(agent_config_file):
            with open(agent_config_file, 'r') as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(agent_config, key):
                        setattr(agent_config, key, value)
    except Exception as e:
        print(f"[control] Failed to load agent config: {e}")
    return agent_config


def save_agent_config() -> None:
    """Save agent configuration to file."""
    global agent_config
    try:
        with open(agent_config_file, 'w') as f:
            json.dump(asdict(agent_config), f, indent=2)
        print(f"[control] Saved agent config to {agent_config_file}")
    except Exception as e:
        print(f"[control] Failed to save agent config: {e}")


def get_mode() -> str:
    """Get current mode from file."""
    try:
        if os.path.exists(mode_file):
            with open(mode_file, 'r') as f:
                return f.read().strip()
    except Exception:
        pass
    return "MANUAL"


def set_mode(mode: str) -> None:
    """Set mode to file."""
    try:
        with open(mode_file, 'w') as f:
            f.write(mode)
        socketio.emit('mode_update', {'mode': mode})
        print(f"[control] Mode set to: {mode}")
    except Exception as e:
        print(f"[control] Failed to set mode: {e}")


# --- SERIAL COMMUNICATION ---
def connect_serial(port: str = None, baud: int = 115200) -> bool:
    """Connect to Arduino via serial."""
    if port is None:
        port = get_default_serial_port()
    global serial_connection
    try:
        serial_connection = serial.Serial(port, baud, timeout=0.1)
        print(f"[control] Connected to serial: {port}")
        return True
    except Exception as e:
        print(f"[control] Serial connection failed: {e}")
        return False


def send_config_to_arduino() -> None:
    """Send current configuration to Arduino via serial."""
    global serial_connection
    if serial_connection is None or not serial_connection.is_open:
        return
    
    try:
        # Send motor configs
        for i, motor in enumerate([robot_config.motor1, robot_config.motor2], 1):
            cmd = f"<CONFIG,MOTOR{i},MIN_SPEED,{motor.min_speed}>\n"
            serial_connection.write(cmd.encode())
            time.sleep(0.05)
            
            cmd = f"<CONFIG,MOTOR{i},MAX_SPEED,{motor.max_speed}>\n"
            serial_connection.write(cmd.encode())
            time.sleep(0.05)
            
            cmd = f"<CONFIG,MOTOR{i},INVERT,{str(motor.invert_direction).lower()}>\n"
            serial_connection.write(cmd.encode())
            time.sleep(0.05)
        
        # Send safety config
        cmd = f"<CONFIG,SAFETY,STOP_DIST,{robot_config.safety.stop_distance}>\n"
        serial_connection.write(cmd.encode())
        time.sleep(0.05)
        
        cmd = f"<CONFIG,SAFETY,MAX_SPEED,{robot_config.safety.max_speed_limit}>\n"
        serial_connection.write(cmd.encode())
        time.sleep(0.05)
        
        # Send servo config
        cmd = f"<CONFIG,SERVO,SCAN_RANGE,{robot_config.servo.scan_range}>\n"
        serial_connection.write(cmd.encode())
        time.sleep(0.05)
        
        # Save to EEPROM
        cmd = "<CONFIG,SAVE>\n"
        serial_connection.write(cmd.encode())
        
        print("[control] Configuration sent to Arduino")
    except Exception as e:
        print(f"[control] Failed to send config to Arduino: {e}")


def send_emergency_stop() -> None:
    """Send emergency stop to Arduino."""
    global serial_connection
    if serial_connection is None or not serial_connection.is_open:
        return
    
    try:
        cmd = "<1,S,0>\n<2,S,0>\n"
        serial_connection.write(cmd.encode())
        set_mode("E-STOP")
        print("[control] Emergency stop sent")
    except Exception as e:
        print(f"[control] Failed to send emergency stop: {e}")


# --- FLASK ROUTES ---
@app.route('/')
def index():
    """Serve the control center UI."""
    return render_template('index.html')


# --- CONFIGURATION API ---
@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current robot configuration."""
    return jsonify(asdict(robot_config))


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update robot configuration."""
    global robot_config
    try:
        data = request.json
        
        # Update motor configs
        if 'motor1' in data:
            for key, value in data['motor1'].items():
                if hasattr(robot_config.motor1, key):
                    setattr(robot_config.motor1, key, value)
        
        if 'motor2' in data:
            for key, value in data['motor2'].items():
                if hasattr(robot_config.motor2, key):
                    setattr(robot_config.motor2, key, value)
        
        # Update safety config
        if 'safety' in data:
            for key, value in data['safety'].items():
                if hasattr(robot_config.safety, key):
                    setattr(robot_config.safety, key, value)
        
        # Update servo config
        if 'servo' in data:
            for key, value in data['servo'].items():
                if hasattr(robot_config.servo, key):
                    setattr(robot_config.servo, key, value)
        
        save_robot_config()
        send_config_to_arduino()
        
        return jsonify({'status': 'success', 'config': asdict(robot_config)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/config/save', methods=['POST'])
def save_config():
    """Save configuration to file."""
    try:
        save_robot_config()
        send_config_to_arduino()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/config/load', methods=['POST'])
def load_config():
    """Load configuration from file."""
    global robot_config
    try:
        robot_config = load_robot_config()
        send_config_to_arduino()
        return jsonify({'status': 'success', 'config': asdict(robot_config)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/config/reset', methods=['POST'])
def reset_config():
    """Reset configuration to defaults."""
    global robot_config
    try:
        robot_config = RobotConfig()
        save_robot_config()
        send_config_to_arduino()
        return jsonify({'status': 'success', 'config': asdict(robot_config)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


# --- AGENT API ---
@app.route('/api/agent/config', methods=['GET'])
def get_agent_config():
    """Get agent configuration."""
    return jsonify(asdict(agent_config))


@app.route('/api/agent/config', methods=['POST'])
def update_agent_config():
    """Update agent configuration."""
    global agent_config
    try:
        data = request.json
        for key, value in data.items():
            if hasattr(agent_config, key):
                setattr(agent_config, key, value)
        save_agent_config()
        return jsonify({'status': 'success', 'config': asdict(agent_config)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/agent/mode', methods=['GET'])
def get_mode_api():
    """Get current mode."""
    return jsonify({'mode': get_mode()})


@app.route('/api/agent/mode', methods=['POST'])
def set_mode_api():
    """Set mode."""
    try:
        data = request.json
        mode = data.get('mode', 'MANUAL')
        set_mode(mode)
        return jsonify({'status': 'success', 'mode': mode})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/agent/command', methods=['POST'])
def send_agent_command():
    """Send command to agent."""
    try:
        data = request.json
        command_type = data.get('type', 'navigation')
        parameters = data.get('parameters', {})
        
        # For now, just log the command
        # In a full implementation, this would communicate with the agent controller
        print(f"[control] Agent command: {command_type}, params: {parameters}")
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


# --- TELEMETRY API ---
@app.route('/api/telemetry', methods=['GET'])
def get_telemetry():
    """Get current telemetry state."""
    telemetry.last_update = datetime.now().isoformat()
    return jsonify(asdict(telemetry))


# --- EMERGENCY CONTROLS ---
@app.route('/api/emergency/stop', methods=['POST'])
def emergency_stop():
    """Trigger emergency stop."""
    try:
        send_emergency_stop()
        socketio.emit('emergency_stop', {'timestamp': datetime.now().isoformat()})
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/emergency/reset', methods=['POST'])
def emergency_reset():
    """Reset from emergency stop."""
    try:
        set_mode("MANUAL")
        socketio.emit('mode_update', {'mode': 'MANUAL'})
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


# --- SERIAL PORTS API ---
@app.route('/api/serial/ports', methods=['GET'])
def list_serial_ports():
    """List available serial ports."""
    ports = []
    for port in serial.tools.list_ports.comports():
        ports.append({
            'device': port.device,
            'description': port.description,
            'hwid': port.hwid
        })
    return jsonify({'ports': ports})


@app.route('/api/serial/connect', methods=['POST'])
def connect_serial_api():
    """Connect to serial port."""
    try:
        data = request.json
        port = data.get('port', get_default_serial_port())
        baud = data.get('baud', 115200)
        success = connect_serial(port, baud)
        if success:
            send_config_to_arduino()
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


# --- WEBSOCKET EVENTS ---
@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    emit('telemetry_update', asdict(telemetry))
    emit('mode_update', {'mode': get_mode()})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    pass


@socketio.on('request_telemetry')
def handle_telemetry_request():
    """Handle telemetry request."""
    telemetry.last_update = datetime.now().isoformat()
    emit('telemetry_update', asdict(telemetry))


# --- TELEMETRY UPDATE THREAD ---
def telemetry_update_thread():
    """Background thread to update telemetry from serial."""
    global serial_connection, telemetry
    
    while True:
        if serial_connection and serial_connection.is_open:
            try:
                if serial_connection.in_waiting > 0:
                    line = serial_connection.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        # Parse telemetry from Arduino
                        if line.startswith('<DISTANCE,'):
                            try:
                                distance = int(line[len('<DISTANCE,'):-1])
                                telemetry.ultrasonic_distance = distance
                                socketio.emit('telemetry_update', asdict(telemetry))
                            except ValueError:
                                pass
            except Exception as e:
                print(f"[control] Telemetry read error: {e}")
        
        time.sleep(0.1)


# --- MAIN ---
def main():
    parser = argparse.ArgumentParser(description="Robot Control Center Web Server")
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--serial-port', default=get_default_serial_port(), help='Serial port for Arduino')
    parser.add_argument('--baud', type=int, default=115200, help='Serial baud rate')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Load configurations
    load_robot_config()
    load_agent_config()
    
    # Connect to serial
    connect_serial(args.serial_port, args.baud)
    
    # Start telemetry thread
    telemetry_thread = threading.Thread(target=telemetry_update_thread, daemon=True)
    telemetry_thread.start()
    
    print(f"[control] Starting control center on {args.host}:{args.port}")
    
    # Create templates directory if it doesn't exist
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
        print(f"[control] Created templates directory: {templates_dir}")
    
    # Run Flask app
    socketio.run(app, host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
