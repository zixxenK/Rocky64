#!/usr/bin/env python3
"""
unified_dashboard.py — Unified robot control dashboard with integrated services.

Features:
- Web-based configuration and control (extends control_center.py)
- Integrated agent controller as background service
- Camera stream endpoint (ESP32/USB/ROS2)
- System status monitoring (ROS2, SSH, Serial, Camera, Agent)
- Boot orchestrator for starting all subsystems
- Cross-platform support (Windows/Linux/Rock64)
- WebSocket real-time updates
- Manual control interface (virtual joystick, keyboard, PS5)

Usage:
  python host_control/unified_dashboard.py
  python host_control/unified_dashboard.py --port 5000
  python host_control/unified_dashboard.py --boot-all
"""

import argparse
import json
import os
import sys
import threading
import time
import subprocess
import signal
import requests
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from queue import Queue

from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit
import serial
import serial.tools.list_ports
import cv2
import numpy as np

# Import platform utilities for cross-platform compatibility
from platform_utils import get_default_serial_port, get_platform, get_ssh_key_path


# --- MODES ---
class Mode(Enum):
    MANUAL = "MANUAL"
    AGENT = "AGENT"
    E_STOP = "E-STOP"


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
    camera_index: int = 0
    rock64_host: str = "192.168.1.159"
    rock64_port: str = get_default_serial_port()
    ssh_key: str = get_ssh_key_path()


@dataclass
class DashboardConfig:
    platform: str = "auto"
    ros2_enabled: bool = True
    agent_enabled: bool = True
    camera_source: str = "esp32"  # esp32, usb, ros2
    camera_url: str = "http://192.168.1.153/stream"
    camera_index: int = 0
    manual_control: str = "virtual_joystick"  # virtual_joystick, keyboard, ps5
    auto_boot: bool = False
    ros2_workspace: str = ""
    ros2_launch_file: str = "rock64_bringup.launch.py"
    
    # Connection retry settings
    max_retries: int = 5
    retry_delay: float = 2.0
    
    # Ollama/LM Studio settings
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    wait_for_ollama: bool = True
    ollama_timeout: float = 30.0
    
    # AI Control Node settings
    lm_studio_url: str = "http://192.168.1.81:1234/v1"
    ai_enabled: bool = True
    ai_loop_rate: float = 0.5  # Hz
    ai_robot_config: str = "config/robot_registry.yaml"
    
    # Camera settings
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    jpeg_quality: int = 85


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


@dataclass
class SystemStatus:
    ros2_running: bool = False
    ssh_connected: bool = False
    serial_connected: bool = False
    camera_running: bool = False
    agent_running: bool = False
    platform: str = "unknown"
    boot_progress: str = "idle"
    boot_errors: list = None
    agent_pid: int = None
    ssh_host: str = None
    ollama_ready: bool = False
    ai_node_running: bool = False
    ai_node_pid: int = None
    ai_thinking: str = ""
    ai_decision: str = ""
    
    def __post_init__(self):
        if self.boot_errors is None:
            self.boot_errors = []


# --- FLASK APP ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'robot-control-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- GLOBAL STATE ---
config_dir = os.path.dirname(__file__)
config_file = os.path.join(config_dir, "robot_config.json")
agent_config_file = os.path.join(config_dir, "agent_config.json")
dashboard_config_file = os.path.join(config_dir, "dashboard_config.json")
mode_file = os.path.join(config_dir, "agent_mode.txt")

robot_config = RobotConfig()
agent_config = AgentConfig()
dashboard_config = DashboardConfig()
telemetry = TelemetryState()
system_status = SystemStatus()
serial_connection: Optional[serial.Serial] = None
camera: Optional[cv2.VideoCapture] = None
agent_process: Optional[subprocess.Popen] = None
ros2_process: Optional[subprocess.Popen] = None
ssh_proc: Optional[subprocess.Popen] = None
ai_node_process: Optional[subprocess.Popen] = None

# Thread-safe queues for inter-service communication
command_queue = Queue()
telemetry_queue = Queue()


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
        print(f"[dashboard] Failed to load config: {e}")
    return robot_config


def save_robot_config() -> None:
    """Save robot configuration to file."""
    global robot_config
    try:
        with open(config_file, 'w') as f:
            json.dump(asdict(robot_config), f, indent=2)
        print(f"[dashboard] Saved config to {config_file}")
    except Exception as e:
        print(f"[dashboard] Failed to save config: {e}")


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
        print(f"[dashboard] Failed to load agent config: {e}")
    return agent_config


def save_agent_config() -> None:
    """Save agent configuration to file."""
    global agent_config
    try:
        with open(agent_config_file, 'w') as f:
            json.dump(asdict(agent_config), f, indent=2)
        print(f"[dashboard] Saved agent config to {agent_config_file}")
    except Exception as e:
        print(f"[dashboard] Failed to save agent config: {e}")


def load_dashboard_config() -> DashboardConfig:
    """Load dashboard configuration from file."""
    global dashboard_config
    try:
        if os.path.exists(dashboard_config_file):
            with open(dashboard_config_file, 'r') as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(dashboard_config, key):
                        setattr(dashboard_config, key, value)
    except Exception as e:
        print(f"[dashboard] Failed to load dashboard config: {e}")
    return dashboard_config


def save_dashboard_config() -> None:
    """Save dashboard configuration to file."""
    global dashboard_config
    try:
        with open(dashboard_config_file, 'w') as f:
            json.dump(asdict(dashboard_config), f, indent=2)
        print(f"[dashboard] Saved dashboard config to {dashboard_config_file}")
    except Exception as e:
        print(f"[dashboard] Failed to save dashboard config: {e}")


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
        telemetry.mode = mode
        socketio.emit('mode_update', {'mode': mode})
        socketio.emit('telemetry_update', asdict(telemetry))
        print(f"[dashboard] Mode set to: {mode}")
    except Exception as e:
        print(f"[dashboard] Failed to set mode: {e}")


# --- SERIAL COMMUNICATION ---
def connect_serial(port: str = None, baud: int = 115200) -> bool:
    """Connect to Arduino via serial."""
    if port is None:
        port = get_default_serial_port()
    global serial_connection
    try:
        serial_connection = serial.Serial(port, baud, timeout=0.1)
        system_status.serial_connected = True
        print(f"[dashboard] Connected to serial: {port}")
        emit_system_status()
        return True
    except Exception as e:
        print(f"[dashboard] Serial connection failed: {e}")
        system_status.serial_connected = False
        emit_system_status()
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
        
        print("[dashboard] Configuration sent to Arduino")
    except Exception as e:
        print(f"[dashboard] Failed to send config to Arduino: {e}")


def send_emergency_stop() -> None:
    """Send emergency stop to Arduino (via serial or SSH)."""
    global serial_connection, ssh_proc
    
    # Try local serial first
    if serial_connection is not None and serial_connection.is_open:
        try:
            cmd = "<1,S,0>\n<2,S,0>\n"
            serial_connection.write(cmd.encode())
            set_mode("E-STOP")
            print("[dashboard] Emergency stop sent via serial")
            return
        except Exception as e:
            print(f"[dashboard] Failed to send emergency stop via serial: {e}")
    
    # Fallback to SSH (Windows or when serial unavailable)
    if ssh_proc is not None and ssh_proc.poll() is None:
        try:
            cmd = "<1,S,0>\n<2,S,0>\n"
            ssh_proc.stdin.write(cmd.encode())
            ssh_proc.stdin.flush()
            set_mode("E-STOP")
            print("[dashboard] Emergency stop sent via SSH")
            return
        except Exception as e:
            print(f"[dashboard] Failed to send emergency stop via SSH: {e}")
    
    print(f"[dashboard] No connection available for emergency stop")


def send_motor_command(motor_id: int, direction: str, speed: int) -> None:
    """Send motor command to Arduino (via serial or SSH)."""
    global serial_connection, ssh_proc
    
    cmd = f"<{motor_id},{direction},{speed}>\n"
    
    # Try local serial first
    if serial_connection is not None and serial_connection.is_open:
        try:
            serial_connection.write(cmd.encode())
            print(f"[dashboard] Motor command sent via serial: {cmd.strip()}")
            return
        except Exception as e:
            print(f"[dashboard] Failed to send motor command via serial: {e}")
    
    # Fallback to SSH (Windows or when serial unavailable)
    if ssh_proc is not None and ssh_proc.poll() is None:
        try:
            ssh_proc.stdin.write(cmd.encode())
            ssh_proc.stdin.flush()
            print(f"[dashboard] Motor command sent via SSH: {cmd.strip()}")
            return
        except Exception as e:
            print(f"[dashboard] Failed to send motor command via SSH: {e}")
    
    print(f"[dashboard] No connection available for motor command: {cmd.strip()}")


def send_servo_command(position: int) -> None:
    """Send servo command to Arduino (via serial or SSH)."""
    global serial_connection, ssh_proc
    
    cmd = f"<SERVO,{position}>\n"
    
    # Try local serial first
    if serial_connection is not None and serial_connection.is_open:
        try:
            serial_connection.write(cmd.encode())
            telemetry.servo_position = position
            print(f"[dashboard] Servo command sent via serial: {cmd.strip()}")
            return
        except Exception as e:
            print(f"[dashboard] Failed to send servo command via serial: {e}")
    
    # Fallback to SSH (Windows or when serial unavailable)
    if ssh_proc is not None and ssh_proc.poll() is None:
        try:
            ssh_proc.stdin.write(cmd.encode())
            ssh_proc.stdin.flush()
            telemetry.servo_position = position
            print(f"[dashboard] Servo command sent via SSH: {cmd.strip()}")
            return
        except Exception as e:
            print(f"[dashboard] Failed to send servo command via SSH: {e}")
    
    print(f"[dashboard] No connection available for servo command: {cmd.strip()}")


# --- CAMERA STREAM ---
def get_available_cameras() -> list:
    """Get list of available USB cameras."""
    available = []
    for i in range(4):  # Check first 4 camera indices
        try:
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                # Get camera info
                width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                available.append({
                    'index': i,
                    'width': int(width),
                    'height': int(height),
                    'name': f'Camera {i}'
                })
                cap.release()
        except Exception:
            pass
    return available


def init_camera() -> bool:
    """Initialize camera based on configuration."""
    global camera
    try:
        if dashboard_config.camera_source == "usb":
            camera = cv2.VideoCapture(dashboard_config.camera_index)
            if camera.isOpened():
                # Set camera properties from config
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, dashboard_config.camera_width)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, dashboard_config.camera_height)
                camera.set(cv2.CAP_PROP_FPS, dashboard_config.camera_fps)
                
                # Verify settings were applied
                actual_width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
                actual_fps = int(camera.get(cv2.CAP_PROP_FPS))
                
                system_status.camera_running = True
                print(f"[dashboard] Camera initialized: USB {dashboard_config.camera_index} ({actual_width}x{actual_height} @ {actual_fps}fps)")
                emit_system_status()
                return True
            else:
                print(f"[dashboard] Failed to open USB camera {dashboard_config.camera_index}")
        elif dashboard_config.camera_source == "esp32":
            # ESP32 camera is accessed via HTTP stream, handled in stream endpoint
            system_status.camera_running = True
            print(f"[dashboard] ESP32 camera configured: {dashboard_config.camera_url}")
            emit_system_status()
            return True
        elif dashboard_config.camera_source == "ros2":
            # ROS2 camera would be handled via ROS2 subscription
            system_status.camera_running = True
            print("[dashboard] ROS2 camera configured")
            emit_system_status()
            return True
    except Exception as e:
        print(f"[dashboard] Camera init error: {e}")
        system_status.camera_running = False
        emit_system_status()
    return False


def get_camera_frame() -> Optional[np.ndarray]:
    """Get a frame from the camera."""
    global camera
    if camera is None or not camera.isOpened():
        return None
    try:
        ret, frame = camera.read()
        if ret:
            return frame
    except Exception as e:
        print(f"[dashboard] Camera read error: {e}")
    return None


# --- AGENT SERVICE ---
def start_agent_service() -> bool:
    """Start agent controller as subprocess."""
    global agent_process
    try:
        cmd = [
            sys.executable,
            os.path.join(config_dir, "agent_controller.py"),
            "--camera", str(dashboard_config.camera_index),
            "--rock64-host", agent_config.rock64_host,
            "--forward-speed", str(agent_config.forward_speed),
            "--turn-speed", str(agent_config.turn_speed),
        ]
        
        agent_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        system_status.agent_running = True
        system_status.agent_pid = agent_process.pid
        print(f"[dashboard] Agent service started (PID: {agent_process.pid})")
        emit_system_status()
        return True
    except Exception as e:
        print(f"[dashboard] Failed to start agent service: {e}")
        system_status.agent_running = False
        system_status.agent_pid = None
        emit_system_status()
        return False


def stop_agent_service() -> bool:
    """Stop agent controller subprocess."""
    global agent_process, ps5_monitor_running
    try:
        # Stop the PS5 monitor thread to prevent auto-restart
        ps5_monitor_running = False
        
        if agent_process is not None:
            agent_process.terminate()
            agent_process.wait(timeout=5)
            agent_process = None
            system_status.agent_running = False
            system_status.agent_pid = None
            print("[dashboard] Agent service stopped")
            emit_system_status()
            return True
    except Exception as e:
        print(f"[dashboard] Failed to stop agent service: {e}")
        return False
    return False


def restart_agent_service() -> bool:
    """Restart agent controller subprocess."""
    stop_agent_service()
    time.sleep(1)
    return start_agent_service()


# --- PS5 CONTROLLER SERVICE ---
ps5_monitor_thread = None
ps5_monitor_running = False

def monitor_ps5_service():
    """Background thread to monitor PS5 controller service and restart if it crashes."""
    global ps5_monitor_running, agent_process
    restart_count = 0
    max_restarts = 10  # Increased from 3 to allow more restart attempts
    consecutive_failures = 0
    max_consecutive_failures = 5  # Increased from 2
    
    while ps5_monitor_running:
        try:
            time.sleep(10)  # Increased from 5 to 10 seconds to reduce interference
            
            if agent_process is None:
                continue
                
            # Check if process is still running
            if agent_process.poll() is not None:
                # Process has died - don't call communicate() as it can interfere
                print(f"[dashboard] PS5 controller service process ended (exit code: {agent_process.poll()})")
                
                if restart_count < max_restarts:
                    restart_count += 1
                    print(f"[dashboard] Attempting to restart PS5 service (attempt {restart_count}/{max_restarts})...")
                    time.sleep(3)  # Increased from 2 to 3 seconds
                    if start_ps5_service():
                        print(f"[dashboard] PS5 service restarted successfully")
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        print(f"[dashboard] Failed to restart PS5 service")
                        if consecutive_failures >= max_consecutive_failures:
                            print(f"[dashboard] Multiple consecutive failures ({consecutive_failures}). Stopping auto-restart.")
                            system_status.agent_running = False
                            emit_system_status()
                            ps5_monitor_running = False
                else:
                    print(f"[dashboard] Max restart attempts ({max_restarts}) reached. Giving up.")
                    system_status.agent_running = False
                    emit_system_status()
                    ps5_monitor_running = False
        except Exception as e:
            print(f"[dashboard] Error in PS5 monitor thread: {e}")
            time.sleep(10)

def start_ps5_service() -> bool:
    """Start PS5 controller service (windows_control.py)."""
    global agent_process, ps5_monitor_thread, ps5_monitor_running  # Reuse agent_process for PS5 controller
    try:
        windows_control_script = os.path.join(config_dir, "windows_control.py")
        if not os.path.exists(windows_control_script):
            print(f"[dashboard] windows_control.py not found: {windows_control_script}")
            return False
        
        cmd = [
            sys.executable,
            windows_control_script,
            "--host", agent_config.rock64_host,
        ]
        
        print(f"[dashboard] Starting PS5 controller service: {' '.join(cmd)}")
        # Don't pipe stdout/stderr to avoid buffer issues that can cause process hangs
        agent_process = subprocess.Popen(
            cmd,
            stdout=None,  # Let it inherit stdout
            stderr=None,  # Let it inherit stderr
            text=True
        )
        
        # Wait longer to see if it starts successfully (increased from 2 to 5 seconds)
        time.sleep(5)
        
        if agent_process.poll() is not None:
            # Process exited
            print(f"[dashboard] PS5 controller service exited (exit code: {agent_process.poll()})")
            system_status.agent_running = False
            emit_system_status()
            return False
        
        system_status.agent_running = True
        system_status.agent_pid = agent_process.pid
        print(f"[dashboard] PS5 controller service started (PID: {agent_process.pid})")
        emit_system_status()
        
        # Start monitor thread if not already running
        if ps5_monitor_thread is None or not ps5_monitor_thread.is_alive():
            ps5_monitor_running = True
            ps5_monitor_thread = threading.Thread(target=monitor_ps5_service, daemon=True)
            ps5_monitor_thread.start()
            print(f"[dashboard] PS5 service monitor thread started")
        
        return True
    except Exception as e:
        print(f"[dashboard] Failed to start PS5 controller service: {e}")
        system_status.agent_running = False
        emit_system_status()
        return False


# --- ROS2 SERVICE ---
def start_ros2_service() -> bool:
    """Start ROS2 launch as subprocess (Linux only)."""
    global ros2_process
    if get_platform() != "linux":
        print("[dashboard] ROS2 service not available on Windows")
        return False
    
    try:
        if not dashboard_config.ros2_workspace:
            print("[dashboard] ROS2 workspace not configured")
            return False
        
        cmd = [
            "bash",
            "-c",
            f"cd {dashboard_config.ros2_workspace} && "
            f"source install/setup.bash && "
            f"ros2 launch robot_bringup {dashboard_config.ros2_launch_file}"
        ]
        
        ros2_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        system_status.ros2_running = True
        print(f"[dashboard] ROS2 service started (PID: {ros2_process.pid})")
        emit_system_status()
        return True
    except Exception as e:
        print(f"[dashboard] Failed to start ROS2 service: {e}")
        system_status.ros2_running = False
        emit_system_status()
        return False


def stop_ros2_service() -> bool:
    """Stop ROS2 launch subprocess."""
    global ros2_process
    try:
        if ros2_process is not None:
            ros2_process.terminate()
            ros2_process.wait(timeout=10)
            ros2_process = None
            system_status.ros2_running = False
            print("[dashboard] ROS2 service stopped")
            emit_system_status()
            return True
    except Exception as e:
        print(f"[dashboard] Failed to stop ROS2 service: {e}")
        return False
    return False


# --- AI CONTROL NODE SERVICE ---
def start_ai_node_service() -> bool:
    """Start AI control node service (ai_control_node.py)."""
    global ai_node_process
    try:
        # Check if ROS 2 workspace exists
        ros2_ws = dashboard_config.ros2_workspace
        if not ros2_ws:
            print("[dashboard] ROS 2 workspace not configured")
            return False
        
        ai_node_script = os.path.join(ros2_ws, "src", "robot_control", "robot_control", "ai_control_node.py")
        if not os.path.exists(ai_node_script):
            print(f"[dashboard] AI control node not found: {ai_node_script}")
            return False
        
        # Source ROS 2 environment and run the node
        cmd = [
            "bash",
            "-c",
            f"source {ros2_ws}/install/setup.bash && python3 {ai_node_script}"
        ]
        
        # Add LM Studio URL parameter
        if dashboard_config.lm_studio_url:
            cmd[-1] += f" --ros-args -p lm_studio_url:={dashboard_config.lm_studio_url}"
        
        print(f"[dashboard] Starting AI control node")
        ai_node_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        time.sleep(2)
        
        if ai_node_process.poll() is not None:
            print(f"[dashboard] AI control node exited (exit code: {ai_node_process.poll()})")
            return False
        
        system_status.ai_node_running = True
        system_status.ai_node_pid = ai_node_process.pid
        print(f"[dashboard] AI control node started (PID: {ai_node_process.pid})")
        emit_system_status()
        return True
        
    except Exception as e:
        print(f"[dashboard] Failed to start AI control node: {e}")
        return False


def stop_ai_node_service() -> bool:
    """Stop AI control node service."""
    global ai_node_process
    try:
        if ai_node_process is not None:
            ai_node_process.terminate()
            ai_node_process.wait(timeout=5)
            ai_node_process = None
            print("[dashboard] AI control node stopped")
        
        system_status.ai_node_running = False
        system_status.ai_node_pid = None
        system_status.ai_thinking = ""
        system_status.ai_decision = ""
        emit_system_status()
        return True
    except Exception as e:
        print(f"[dashboard] Failed to stop AI control node: {e}")
        return False


def restart_ai_node_service() -> bool:
    """Restart AI control node service."""
    stop_ai_node_service()
    time.sleep(1)
    return start_ai_node_service()


# --- SSH CONNECTION ---
def init_ssh_connection(max_retries: int = 5, retry_delay: float = 2.0) -> bool:
    """Initialize SSH connection to Rock64 with retry logic."""
    global ssh_proc
    retry_count = 0
    last_error = None
    
    while retry_count < max_retries:
        try:
            ssh_cmd = [
                'ssh',
                '-i', agent_config.ssh_key,
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ServerAliveInterval=5',
                '-o', 'ConnectTimeout=10',
                f'rock64@{agent_config.rock64_host}',
                f'stty -F {agent_config.rock64_port} 115200 raw -echo; cat > {agent_config.rock64_port}',
            ]
            
            ssh_proc = subprocess.Popen(
                ssh_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            time.sleep(1.5)
            if ssh_proc.poll() is not None:
                last_error = "SSH process exited immediately"
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = retry_delay * (2 ** retry_count)  # Exponential backoff
                    print(f"[dashboard] SSH connection failed (attempt {retry_count}/{max_retries}), retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                continue
            
            system_status.ssh_connected = True
            system_status.ssh_host = agent_config.rock64_host
            print(f"[dashboard] SSH connected to Rock64: {agent_config.rock64_host}")
            emit_system_status()
            return True
        except Exception as e:
            last_error = str(e)
            retry_count += 1
            if retry_count < max_retries:
                wait_time = retry_delay * (2 ** retry_count)  # Exponential backoff
                print(f"[dashboard] SSH connection error: {e} (attempt {retry_count}/{max_retries}), retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
    
    print(f"[dashboard] SSH connection failed after {max_retries} attempts. Last error: {last_error}")
    system_status.ssh_connected = False
    emit_system_status()
    return False


def check_ollama_ready() -> bool:
    """Check if Ollama service is ready."""
    try:
        ollama_url = f"http://{dashboard_config.ollama_host}:{dashboard_config.ollama_port}/api/tags"
        response = requests.get(ollama_url, timeout=2.0)
        return response.status_code == 200
    except requests.RequestException:
        return False


def wait_for_ollama() -> bool:
    """Wait for Ollama service to be ready."""
    if not dashboard_config.wait_for_ollama:
        print("[dashboard] Skipping Ollama readiness check")
        system_status.ollama_ready = False
        emit_system_status()
        return True
    
    print(f"[dashboard] Waiting for Ollama at {dashboard_config.ollama_host}:{dashboard_config.ollama_port}...")
    start_time = time.time()
    
    while time.time() - start_time < dashboard_config.ollama_timeout:
        if check_ollama_ready():
            print("[dashboard] Ollama is ready")
            system_status.ollama_ready = True
            emit_system_status()
            return True
        time.sleep(1.0)
    
    print(f"[dashboard] Ollama not ready after {dashboard_config.ollama_timeout}s. Continuing anyway...")
    system_status.ollama_ready = False
    emit_system_status()
    return False


# --- SYSTEM STATUS ---
def update_system_status() -> None:
    """Update system status."""
    system_status.platform = get_platform()
    
    # Check process status
    if agent_process is not None and agent_process.poll() is not None:
        system_status.agent_running = False
        system_status.agent_pid = None
        emit_system_status()
    
    if ros2_process is not None and ros2_process.poll() is not None:
        system_status.ros2_running = False
        emit_system_status()
    
    if ssh_proc is not None and ssh_proc.poll() is not None:
        system_status.ssh_connected = False
        emit_system_status()
    
    if serial_connection is not None and not serial_connection.is_open:
        system_status.serial_connected = False
        emit_system_status()
    
    if ai_node_process is not None and ai_node_process.poll() is not None:
        system_status.ai_node_running = False
        system_status.ai_node_pid = None
        emit_system_status()
    
    # Check Ollama status periodically
    if dashboard_config.wait_for_ollama:
        ollama_status = check_ollama_ready()
        if ollama_status != system_status.ollama_ready:
            system_status.ollama_ready = ollama_status
            emit_system_status()


def emit_system_status() -> None:
    """Emit system status via WebSocket."""
    socketio.emit('system_status', asdict(system_status))


# --- BOOT ORCHESTRATOR ---
def boot_all_services() -> bool:
    """Boot all services in correct order."""
    system_status.boot_progress = "starting"
    system_status.boot_errors = []
    emit_system_status()
    
    try:
        # Step 0: Wait for Ollama if configured
        if dashboard_config.wait_for_ollama:
            system_status.boot_progress = "waiting_ollama"
            emit_system_status()
            wait_for_ollama()
        
        # Step 1: Connect serial (Linux only - Windows uses SSH to Rock64)
        system_status.boot_progress = "connecting_serial"
        emit_system_status()
        if get_platform() == "linux":
            if not connect_serial():
                system_status.boot_errors.append("Serial connection failed")
        
        # Step 2: Connect SSH (Windows always needs SSH, Linux if agent enabled)
        system_status.boot_progress = "connecting_ssh"
        emit_system_status()
        if get_platform() == "windows" or dashboard_config.agent_enabled:
            if not init_ssh_connection(max_retries=dashboard_config.max_retries, retry_delay=dashboard_config.retry_delay):
                system_status.boot_errors.append("SSH connection failed")
        
        # Step 3: Start ROS2 (Linux only)
        if get_platform() == "linux" and dashboard_config.ros2_enabled:
            system_status.boot_progress = "starting_ros2"
            emit_system_status()
            if not start_ros2_service():
                system_status.boot_errors.append("ROS2 service failed")
        
        # Step 4: Initialize camera
        system_status.boot_progress = "initializing_camera"
        emit_system_status()
        if not init_camera():
            system_status.boot_errors.append("Camera initialization failed")
        
        # Step 5: Start agent
        if dashboard_config.agent_enabled:
            system_status.boot_progress = "starting_agent"
            emit_system_status()
            if not start_agent_service():
                system_status.boot_errors.append("Agent service failed")
        
        # Step 6: Start AI node if enabled
        if dashboard_config.ai_enabled:
            system_status.boot_progress = "starting_ai_node"
            emit_system_status()
            if not start_ai_node_service():
                system_status.boot_errors.append("AI node service failed")
        
        system_status.boot_progress = "complete"
        emit_system_status()
        
        if system_status.boot_errors:
            print(f"[dashboard] Boot completed with errors: {system_status.boot_errors}")
        else:
            print("[dashboard] Boot completed successfully")
        
        return len(system_status.boot_errors) == 0
        
    except Exception as e:
        system_status.boot_progress = "failed"
        system_status.boot_errors.append(str(e))
        emit_system_status()
        print(f"[dashboard] Boot failed: {e}")
        return False


def shutdown_all_services() -> bool:
    """Shutdown all services."""
    system_status.boot_progress = "shutting_down"
    emit_system_status()
    
    try:
        stop_agent_service()
        stop_ai_node_service()
        stop_ros2_service()
        
        if ssh_proc is not None:
            try:
                ssh_proc.stdin.close()
            except Exception:
                pass
            ssh_proc.terminate()
        
        if camera is not None:
            camera.release()
        
        if serial_connection is not None:
            serial_connection.close()
        
        system_status.boot_progress = "idle"
        emit_system_status()
        print("[dashboard] All services shut down")
        return True
    except Exception as e:
        print(f"[dashboard] Shutdown failed: {e}")
        return False


# --- FLASK ROUTES ---
@app.route('/')
def index():
    """Serve the unified dashboard UI."""
    return render_template('unified_index.html')


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
        
        if 'motor1' in data:
            for key, value in data['motor1'].items():
                if hasattr(robot_config.motor1, key):
                    setattr(robot_config.motor1, key, value)
        
        if 'motor2' in data:
            for key, value in data['motor2'].items():
                if hasattr(robot_config.motor2, key):
                    setattr(robot_config.motor2, key, value)
        
        if 'safety' in data:
            for key, value in data['safety'].items():
                if hasattr(robot_config.safety, key):
                    setattr(robot_config.safety, key, value)
        
        if 'servo' in data:
            for key, value in data['servo'].items():
                if hasattr(robot_config.servo, key):
                    setattr(robot_config.servo, key, value)
        
        save_robot_config()
        send_config_to_arduino()
        
        return jsonify({'status': 'success', 'config': asdict(robot_config)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


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


@app.route('/api/telemetry', methods=['GET'])
def get_telemetry():
    """Get current telemetry state."""
    telemetry.last_update = datetime.now().isoformat()
    return jsonify(asdict(telemetry))


@app.route('/api/system/status', methods=['GET'])
def get_system_status():
    """Get system status."""
    update_system_status()
    return jsonify(asdict(system_status))


@app.route('/api/system/boot', methods=['POST'])
def boot_system():
    """Boot all services."""
    try:
        success = boot_all_services()
        return jsonify({'status': 'success' if success else 'partial', 'errors': system_status.boot_errors})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/system/shutdown', methods=['POST'])
def shutdown_system():
    """Shutdown all services."""
    try:
        success = shutdown_all_services()
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/agent/start', methods=['POST'])
def start_agent():
    """Start agent service."""
    try:
        success = start_agent_service()
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/agent/stop', methods=['POST'])
def stop_agent():
    """Stop agent service."""
    try:
        success = stop_agent_service()
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/agent/restart', methods=['POST'])
def restart_agent():
    """Restart agent service."""
    try:
        success = restart_agent_service()
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/ai/start', methods=['POST'])
def start_ai_node():
    """Start AI control node service."""
    try:
        success = start_ai_node_service()
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/ai/stop', methods=['POST'])
def stop_ai_node():
    """Stop AI control node service."""
    try:
        success = stop_ai_node_service()
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/ai/restart', methods=['POST'])
def restart_ai_node():
    """Restart AI control node service."""
    try:
        success = restart_ai_node_service()
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/ai/config', methods=['GET'])
def get_ai_config():
    """Get AI configuration."""
    ai_config = {
        'lm_studio_url': dashboard_config.lm_studio_url,
        'ai_enabled': dashboard_config.ai_enabled,
        'ai_loop_rate': dashboard_config.ai_loop_rate,
        'ai_robot_config': dashboard_config.ai_robot_config,
    }
    return jsonify(ai_config)


@app.route('/api/ai/config', methods=['POST'])
def update_ai_config():
    """Update AI configuration."""
    global dashboard_config
    try:
        data = request.json
        if 'lm_studio_url' in data:
            dashboard_config.lm_studio_url = data['lm_studio_url']
        if 'ai_enabled' in data:
            dashboard_config.ai_enabled = data['ai_enabled']
        if 'ai_loop_rate' in data:
            dashboard_config.ai_loop_rate = data['ai_loop_rate']
        if 'ai_robot_config' in data:
            dashboard_config.ai_robot_config = data['ai_robot_config']
        return jsonify({'status': 'success', 'config': {
            'lm_studio_url': dashboard_config.lm_studio_url,
            'ai_enabled': dashboard_config.ai_enabled,
            'ai_loop_rate': dashboard_config.ai_loop_rate,
            'ai_robot_config': dashboard_config.ai_robot_config,
        }})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/ps5/start', methods=['POST'])
def start_ps5():
    """Start PS5 controller service."""
    try:
        success = start_ps5_service()
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/ps5/stop', methods=['POST'])
def stop_ps5():
    """Stop PS5 controller service."""
    try:
        success = stop_agent_service()  # Reuse stop_agent_service
        return jsonify({'status': 'success' if success else 'failed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


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


@app.route('/api/control/motor', methods=['POST'])
def control_motor():
    """Send motor command."""
    try:
        data = request.json
        motor_id = data.get('motor_id', 1)
        direction = data.get('direction', 'S')
        speed = data.get('speed', 0)
        send_motor_command(motor_id, direction, speed)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/control/servo', methods=['POST'])
def control_servo():
    """Send servo command."""
    try:
        data = request.json
        position = data.get('position', 90)
        send_servo_command(position)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/camera/stream')
def camera_stream():
    """MJPEG camera stream endpoint."""
    def generate():
        import requests
        session = requests.Session()
        session.timeout = 2
        
        while True:
            try:
                if dashboard_config.camera_source == "usb":
                    frame = get_camera_frame()
                    if frame is not None:
                        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, dashboard_config.jpeg_quality])
                        if ret:
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
                elif dashboard_config.camera_source == "esp32":
                    # Stream from ESP32 HTTP endpoint
                    try:
                        response = session.get(dashboard_config.camera_url, stream=True, timeout=2)
                        if response.status_code == 200:
                            for chunk in response.iter_content(chunk_size=1024):
                                yield chunk
                    except requests.RequestException as e:
                        # Silently handle stream errors to prevent crash
                        pass
            except Exception as e:
                print(f"[dashboard] Camera stream error: {e}")
                pass
            # Adjust sleep time based on target FPS
            sleep_time = 1.0 / dashboard_config.camera_fps if dashboard_config.camera_fps > 0 else 0.033
            time.sleep(sleep_time)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/cameras', methods=['GET'])
def get_cameras():
    """Get list of available cameras."""
    try:
        cameras = get_available_cameras()
        return jsonify({'cameras': cameras, 'current_source': dashboard_config.camera_source, 'current_index': dashboard_config.camera_index})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/camera/switch', methods=['POST'])
def switch_camera():
    """Switch camera source."""
    try:
        data = request.json
        source = data.get('source', 'usb')
        index = data.get('index', 0)
        
        # Release current camera if USB
        if camera is not None:
            camera.release()
        
        # Update config
        dashboard_config.camera_source = source
        dashboard_config.camera_index = index
        
        # Reinitialize camera
        if init_camera():
            save_dashboard_config()
            return jsonify({'status': 'success', 'source': source, 'index': index})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to initialize camera'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/camera/refresh', methods=['POST'])
def refresh_camera():
    """Refresh camera stream by reinitializing."""
    try:
        # Release current camera
        if camera is not None:
            camera.release()
        
        # Reinitialize camera
        if init_camera():
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to refresh camera'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/camera/settings', methods=['POST'])
def update_camera_settings():
    """Update camera settings."""
    try:
        data = request.json
        dashboard_config.camera_width = data.get('width', 640)
        dashboard_config.camera_height = data.get('height', 480)
        dashboard_config.camera_fps = data.get('fps', 30)
        
        # Validate and clamp JPEG quality to safe range (10-95)
        jpeg_quality = data.get('jpeg_quality', 85)
        dashboard_config.jpeg_quality = max(10, min(95, int(jpeg_quality)))
        
        # Reinitialize camera with new settings
        if camera is not None:
            camera.release()
        
        if init_camera():
            save_dashboard_config()
            return jsonify({'status': 'success', 'settings': {
                'width': dashboard_config.camera_width,
                'height': dashboard_config.camera_height,
                'fps': dashboard_config.camera_fps,
                'jpeg_quality': dashboard_config.jpeg_quality
            }})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to reinitialize camera'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


# --- WEBSOCKET EVENTS ---
@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    emit('telemetry_update', asdict(telemetry))
    emit('mode_update', {'mode': get_mode()})
    emit('system_status', asdict(system_status))


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    pass


@socketio.on('request_telemetry')
def handle_telemetry_request():
    """Handle telemetry request."""
    telemetry.last_update = datetime.now().isoformat()
    emit('telemetry_update', asdict(telemetry))


# --- BACKGROUND THREADS ---
def telemetry_update_thread():
    """Background thread to update telemetry from serial."""
    global serial_connection, telemetry
    
    while True:
        # Only works with local serial connection (Linux)
        # On Windows, ultrasonic data requires SSH forwarding from Rock64
        if serial_connection and serial_connection.is_open:
            try:
                if serial_connection.in_waiting > 0:
                    line = serial_connection.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        if line.startswith('<DISTANCE,'):
                            try:
                                distance = int(line[len('<DISTANCE,'):-1])
                                telemetry.ultrasonic_distance = distance
                                socketio.emit('telemetry_update', asdict(telemetry))
                            except ValueError:
                                pass
            except Exception as e:
                print(f"[dashboard] Telemetry read error: {e}")
        
        time.sleep(0.1)


def system_status_thread():
    """Background thread to update system status."""
    while True:
        update_system_status()
        time.sleep(1)


# --- MAIN ---
def main():
    parser = argparse.ArgumentParser(description="Unified Robot Control Dashboard")
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--serial-port', default=get_default_serial_port(), help='Serial port for Arduino')
    parser.add_argument('--baud', type=int, default=115200, help='Serial baud rate')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--boot-all', action='store_true', help='Boot all services on startup')
    
    # Connection settings
    parser.add_argument('--max-retries', type=int, default=5, help='Max connection retry attempts')
    parser.add_argument('--retry-delay', type=float, default=2.0, help='Initial retry delay (seconds)')
    
    # Ollama settings
    parser.add_argument('--ollama-host', default='localhost', help='Ollama host')
    parser.add_argument('--ollama-port', type=int, default=11434, help='Ollama port')
    parser.add_argument('--wait-for-ollama', action='store_true', default=True, help='Wait for Ollama to be ready')
    parser.add_argument('--no-wait-ollama', action='store_true', help='Skip waiting for Ollama')
    parser.add_argument('--ollama-timeout', type=float, default=30.0, help='Ollama readiness timeout (seconds)')
    
    args = parser.parse_args()
    
    # Load configurations
    load_robot_config()
    load_agent_config()
    load_dashboard_config()
    
    # Override dashboard config with command line args
    dashboard_config.max_retries = args.max_retries
    dashboard_config.retry_delay = args.retry_delay
    dashboard_config.ollama_host = args.ollama_host
    dashboard_config.ollama_port = args.ollama_port
    dashboard_config.wait_for_ollama = args.wait_for_ollama and not args.no_wait_ollama
    dashboard_config.ollama_timeout = args.ollama_timeout
    
    # Update system status
    system_status.platform = get_platform()
    
    # Connect to serial
    connect_serial(args.serial_port, args.baud)
    
    # Initialize camera
    init_camera()
    
    # Boot all services if requested
    if args.boot_all or dashboard_config.auto_boot:
        boot_all_services()
    
    # Start background threads
    telemetry_thread_obj = threading.Thread(target=telemetry_update_thread, daemon=True)
    telemetry_thread_obj.start()
    
    status_thread_obj = threading.Thread(target=system_status_thread, daemon=True)
    status_thread_obj.start()
    
    print(f"[dashboard] Starting unified dashboard on {args.host}:{args.port}")
    print(f"[dashboard] Platform: {system_status.platform}")
    
    # Create templates directory if it doesn't exist
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
        print(f"[dashboard] Created templates directory: {templates_dir}")
    
    # Run Flask app
    socketio.run(app, host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
