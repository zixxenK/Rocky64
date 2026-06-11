#!/usr/bin/env python3
"""
agent_controller.py — AI agent for autonomous robot navigation.

Features:
- Computer vision integration (OpenCV)
- Obstacle detection from camera frames
- Rule-based navigation logic
- Safety monitoring (collision detection)
- Motor command generation
- Mode state management
- Failsafe to manual mode
- Learning parameter tuning

Usage:
  python host_control/agent_controller.py
  python host_control/agent_controller.py --camera 0
  python host_control/agent_controller.py --rock64-host 192.168.1.159
"""

import argparse
import json
import os
import sys
import time
import threading
import subprocess
import requests
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

import cv2
import numpy as np

# Import platform utilities for cross-platform compatibility
from platform_utils import get_default_serial_port, get_ssh_key_path


# --- MODES ---
class Mode(Enum):
    MANUAL = "MANUAL"
    AGENT = "AGENT"
    E_STOP = "E-STOP"


# --- CONFIGURATION ---
@dataclass
class AgentConfig:
    """Agent learning and navigation parameters."""
    # Vision parameters
    obstacle_threshold: int = 100  # Threshold for obstacle detection (0-255)
    min_obstacle_area: int = 500   # Minimum area for obstacle (pixels)
    
    # Navigation parameters
    forward_speed: int = 120       # Default forward speed (PWM)
    turn_speed: int = 80           # Default turn speed (PWM)
    cautious_speed: int = 60       # Speed when obstacle detected
    
    # Safety parameters
    safe_distance: int = 50        # Safe distance from obstacles (cm)
    warning_distance: int = 100    # Warning distance (cm)
    
    # Learning parameters
    exploration_rate: float = 0.1  # Probability of random exploration
    learning_rate: float = 0.01    # Learning rate for parameter updates
    
    # Camera parameters
    camera_index: int = 0          # Camera device index
    frame_width: int = 320         # Camera frame width
    frame_height: int = 240        # Camera frame height
    
    # Rock64 connection
    rock64_host: str = "192.168.1.159"
    rock64_port: str = get_default_serial_port()
    ssh_key: str = get_ssh_key_path()
    
    # Connection retry settings
    max_retries: int = 5
    retry_delay: float = 2.0
    connection_timeout: float = 10.0
    
    # Ollama settings
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    wait_for_ollama: bool = True
    ollama_timeout: float = 30.0


# --- AGENT STATE ---
@dataclass
class AgentState:
    """Current agent state."""
    mode: str = Mode.MANUAL.value
    last_obstacle_detected: bool = False
    obstacle_direction: str = "none"  # left, center, right, none
    last_command: Tuple[int, int, int, int] = (0, 0, 0, 0)  # motor1_dir, motor1_spd, motor2_dir, motor2_spd
    ultrasonic_distance: int = 100  # cm
    
    # Learning metrics
    episodes_completed: int = 0
    collisions_avoided: int = 0
    total_distance_traveled: float = 0.0


class AgentController:
    """Main agent controller for autonomous navigation."""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.state = AgentState()
        self.running = False
        self.camera: Optional[cv2.VideoCapture] = None
        self.ssh_proc: Optional[subprocess.Popen] = None
        self.shutdown_requested = False  # Flag to prevent reconnection during shutdown
        
        # Mode state file
        self.mode_file = os.path.join(os.path.dirname(__file__), "agent_mode.txt")
        self.config_file = os.path.join(os.path.dirname(__file__), "agent_config.json")
        
        # Telemetry state
        self.telemetry_lock = threading.Lock()
        
        # Load saved config if exists
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(self.config, key):
                            setattr(self.config, key, value)
                print(f"[agent] Loaded config from {self.config_file}")
        except Exception as e:
            print(f"[agent] Failed to load config: {e}")
    
    def save_config(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(asdict(self.config), f, indent=2)
            print(f"[agent] Saved config to {self.config_file}")
        except Exception as e:
            print(f"[agent] Failed to save config: {e}")
    
    def load_mode(self) -> str:
        """Load mode from file."""
        try:
            if os.path.exists(self.mode_file):
                with open(self.mode_file, 'r') as f:
                    return f.read().strip()
        except Exception:
            pass
        return Mode.MANUAL.value
    
    def save_mode(self, mode: str) -> None:
        """Save mode to file."""
        try:
            with open(self.mode_file, 'w') as f:
                f.write(mode)
        except Exception:
            pass
    
    def init_camera(self) -> bool:
        """Initialize camera for computer vision."""
        try:
            self.camera = cv2.VideoCapture(self.config.camera_index)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
            
            if not self.camera.isOpened():
                print(f"[agent] Failed to open camera {self.config.camera_index}")
                return False
            
            print(f"[agent] Camera initialized: {self.config.camera_index}")
            return True
        except Exception as e:
            print(f"[agent] Camera init error: {e}")
            return False
    
    def init_rock64_connection(self) -> bool:
        """Initialize SSH connection to Rock64 for motor commands with retry logic."""
        retry_count = 0
        last_error = None
        
        while retry_count < self.config.max_retries:
            try:
                ssh_cmd = [
                    'ssh',
                    '-i', self.config.ssh_key,
                    '-o', 'StrictHostKeyChecking=no',
                    '-o', 'ServerAliveInterval=5',
                    '-o', 'ConnectTimeout=10',
                    f'rock64@{self.config.rock64_host}',
                    f'stty -F {self.config.rock64_port} 115200 raw -echo; cat > {self.config.rock64_port}',
                ]
                
                self.ssh_proc = subprocess.Popen(
                    ssh_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                
                time.sleep(1.5)
                if self.ssh_proc.poll() is not None:
                    last_error = "SSH process exited immediately"
                    retry_count += 1
                    if retry_count < self.config.max_retries:
                        wait_time = self.config.retry_delay * (2 ** retry_count)  # Exponential backoff
                        print(f"[agent] SSH connection failed (attempt {retry_count}/{self.config.max_retries}), retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                    continue
                
                print(f"[agent] Connected to Rock64: {self.config.rock64_host}")
                return True
            except Exception as e:
                last_error = str(e)
                retry_count += 1
                if retry_count < self.config.max_retries:
                    wait_time = self.config.retry_delay * (2 ** retry_count)  # Exponential backoff
                    print(f"[agent] SSH connection error: {e} (attempt {retry_count}/{self.config.max_retries}), retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
        
        print(f"[agent] SSH connection failed after {self.config.max_retries} attempts. Last error: {last_error}")
        return False
    
    def check_ollama_ready(self) -> bool:
        """Check if Ollama service is ready."""
        try:
            ollama_url = f"http://{self.config.ollama_host}:{self.config.ollama_port}/api/tags"
            response = requests.get(ollama_url, timeout=2.0)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def wait_for_ollama(self) -> bool:
        """Wait for Ollama service to be ready."""
        if not self.config.wait_for_ollama:
            print("[agent] Skipping Ollama readiness check")
            return True
        
        print(f"[agent] Waiting for Ollama at {self.config.ollama_host}:{self.config.ollama_port}...")
        start_time = time.time()
        
        while time.time() - start_time < self.config.ollama_timeout:
            if self.check_ollama_ready():
                print("[agent] Ollama is ready")
                return True
            time.sleep(1.0)
        
        print(f"[agent] Ollama not ready after {self.config.ollama_timeout}s. Continuing anyway...")
        return False
    
    def check_ssh_health(self) -> bool:
        """Check if SSH connection is still healthy."""
        if self.ssh_proc is None:
            return False
        return self.ssh_proc.poll() is None
    
    def reconnect_ssh(self) -> bool:
        """Attempt to reconnect SSH."""
        print("[agent] Attempting SSH reconnection...")
        if self.ssh_proc is not None:
            try:
                self.ssh_proc.terminate()
                self.ssh_proc.wait(timeout=2)
            except:
                pass
            self.ssh_proc = None
        
        return self.init_rock64_connection()
    
    def detect_obstacles(self, frame: np.ndarray) -> Tuple[bool, str, np.ndarray]:
        """Detect obstacles from camera frame using simple color/threshold detection."""
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Apply threshold for obstacle detection
            _, thresh = cv2.threshold(gray, self.config.obstacle_threshold, 255, cv2.THRESH_BINARY_INV)
            
            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter contours by area
            large_contours = [c for c in contours if cv2.contourArea(c) > self.config.min_obstacle_area]
            
            if not large_contours:
                return False, "none", thresh
            
            # Determine obstacle direction based on centroid
            frame_center = self.config.frame_width // 2
            obstacle_detected = False
            direction = "none"
            
            for contour in large_contours:
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    
                    if cx < frame_center - 50:
                        direction = "left"
                    elif cx > frame_center + 50:
                        direction = "right"
                    else:
                        direction = "center"
                    
                    obstacle_detected = True
            
            return obstacle_detected, direction, thresh
            
        except Exception as e:
            print(f"[agent] Obstacle detection error: {e}")
            return False, "none", frame
    
    def navigate(self, obstacle_detected: bool, obstacle_direction: str, 
                 ultrasonic_distance: int) -> Tuple[int, int, int, int]:
        """Generate motor commands based on sensor inputs."""
        
        # Emergency stop if ultrasonic distance is critical
        if ultrasonic_distance < self.config.safe_distance:
            return (0, 0, 0, 0)  # Stop both motors
        
        # If obstacle detected via vision
        if obstacle_detected:
            if obstacle_direction == "center":
                # Obstacle ahead - stop or back up
                return (0, 0, 0, 0)
            elif obstacle_direction == "left":
                # Obstacle on left - turn right
                return (1, 'F', self.config.turn_speed, 2, 'B', self.config.turn_speed)
            elif obstacle_direction == "right":
                # Obstacle on right - turn left
                return (1, 'B', self.config.turn_speed, 2, 'F', self.config.turn_speed)
            else:
                # Unknown direction - stop
                return (0, 0, 0, 0)
        
        # No obstacle detected - move forward
        # Slow down if ultrasonic distance is in warning range
        speed = self.config.cautious_speed if ultrasonic_distance < self.config.warning_distance else self.config.forward_speed
        
        # Add exploration with small probability
        if np.random.random() < self.config.exploration_rate:
            # Random turn
            turn_dir = np.random.choice(['left', 'right'])
            if turn_dir == 'left':
                return (1, 'B', self.config.turn_speed, 2, 'F', self.config.turn_speed)
            else:
                return (1, 'F', self.config.turn_speed, 2, 'B', self.config.turn_speed)
        
        # Forward movement
        return (1, 'F', speed, 2, 'F', speed)
    
    def send_motor_command(self, motor_id: int, direction: str, speed: int) -> None:
        """Send motor command to Rock64 via SSH."""
        if self.ssh_proc is None:
            return
        
        try:
            packet = f"<{motor_id},{direction},{speed}>\n".encode()
            self.ssh_proc.stdin.write(packet)
            self.ssh_proc.stdin.flush()
        except Exception as e:
            print(f"[agent] Failed to send motor command: {e}")
    
    def send_stop(self) -> None:
        """Send stop command to both motors."""
        self.send_motor_command(1, 'S', 0)
        self.send_motor_command(2, 'S', 0)
    
    def update_telemetry(self, ultrasonic_distance: int) -> None:
        """Update telemetry state."""
        with self.telemetry_lock:
            self.state.ultrasonic_distance = ultrasonic_distance
    
    def run(self) -> None:
        """Main agent control loop."""
        print("[agent] Starting agent controller...")
        
        # Wait for Ollama if configured
        self.wait_for_ollama()
        
        # Initialize subsystems
        if not self.init_camera():
            print("[agent] WARNING: Camera failed to initialize, running without vision")
        
        if not self.init_rock64_connection():
            print("[agent] ERROR: Failed to connect to Rock64")
            return
        
        self.running = True
        last_mode_check = time.time()
        last_health_check = time.time()
        health_check_interval = 5.0  # Check connection health every 5 seconds
        
        print("[agent] Agent controller running")
        print("[agent] Press Ctrl+C to stop")
        
        try:
            while self.running:
                # Check mode periodically
                if time.time() - last_mode_check > 0.5:
                    current_mode = self.load_mode()
                    if current_mode != self.state.mode:
                        self.state.mode = current_mode
                        print(f"[agent] Mode changed to: {current_mode}")
                        
                        # Send stop on mode change
                        if current_mode == Mode.MANUAL.value or current_mode == Mode.E_STOP.value:
                            self.send_stop()
                    
                    last_mode_check = time.time()
                
                # Check connection health periodically
                if time.time() - last_health_check > health_check_interval:
                    if not self.check_ssh_health() and not self.shutdown_requested:
                        print("[agent] SSH connection lost, attempting reconnection...")
                        if self.reconnect_ssh():
                            print("[agent] SSH reconnection successful")
                        else:
                            print("[agent] SSH reconnection failed, will retry on next health check")
                    last_health_check = time.time()
                
                # Only run navigation in AGENT mode
                if self.state.mode != Mode.AGENT.value:
                    time.sleep(0.1)
                    continue
                
                # Capture camera frame
                frame = None
                if self.camera is not None and self.camera.isOpened():
                    ret, frame = self.camera.read()
                    if not ret:
                        frame = None
                
                # Detect obstacles
                obstacle_detected = False
                obstacle_direction = "none"
                processed_frame = None
                
                if frame is not None:
                    obstacle_detected, obstacle_direction, processed_frame = self.detect_obstacles(frame)
                    
                    # Update state
                    self.state.last_obstacle_detected = obstacle_detected
                    self.state.obstacle_direction = obstacle_direction
                    
                    # Display processed frame (optional, for debugging)
                    # cv2.imshow('Agent Vision', processed_frame)
                    # cv2.waitKey(1)
                
                # Generate navigation command
                motor1_id, motor1_dir, motor1_spd, motor2_id, motor2_dir, motor2_spd = self.navigate(
                    obstacle_detected, obstacle_direction, self.state.ultrasonic_distance
                )
                
                # Send motor commands
                self.send_motor_command(motor1_id, motor1_dir, motor1_spd)
                self.send_motor_command(motor2_id, motor2_dir, motor2_spd)
                
                # Update state
                self.state.last_command = (motor1_id, motor1_dir, motor1_spd, motor2_id, motor2_dir, motor2_spd)
                
                # Small delay to control loop rate
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            print("\n[agent] Stopping agent controller...")
        finally:
            self.cleanup()
    
    def cleanup(self) -> None:
        """Clean up resources."""
        self.shutdown_requested = True  # Prevent reconnection attempts
        self.running = False
        self.send_stop()
        
        if self.camera is not None:
            self.camera.release()
        
        if self.ssh_proc is not None:
            try:
                self.ssh_proc.stdin.close()
            except Exception:
                pass
            self.ssh_proc.terminate()
        
        cv2.destroyAllWindows()
        print("[agent] Agent controller stopped")


def main():
    parser = argparse.ArgumentParser(
        description="AI Agent Controller for autonomous robot navigation"
    )
    parser.add_argument('--camera', type=int, default=0, help='Camera device index')
    parser.add_argument('--rock64-host', default='192.168.1.159', help='Rock64 IP address')
    parser.add_argument('--rock64-port', default=get_default_serial_port(), help='Serial port on Rock64')
    parser.add_argument('--ssh-key', default=get_ssh_key_path(),
                        help='Path to SSH private key')
    parser.add_argument('--forward-speed', type=int, default=120, help='Forward speed (PWM)')
    parser.add_argument('--turn-speed', type=int, default=80, help='Turn speed (PWM)')
    parser.add_argument('--safe-distance', type=int, default=50, help='Safe distance (cm)')
    parser.add_argument('--no-vision', action='store_true', help='Run without computer vision')
    
    # Connection settings
    parser.add_argument('--max-retries', type=int, default=5, help='Max connection retry attempts')
    parser.add_argument('--retry-delay', type=float, default=2.0, help='Initial retry delay (seconds)')
    parser.add_argument('--connection-timeout', type=float, default=10.0, help='Connection timeout (seconds)')
    
    # Ollama settings
    parser.add_argument('--ollama-host', default='localhost', help='Ollama host')
    parser.add_argument('--ollama-port', type=int, default=11434, help='Ollama port')
    parser.add_argument('--wait-for-ollama', action='store_true', default=True, help='Wait for Ollama to be ready')
    parser.add_argument('--no-wait-ollama', action='store_true', help='Skip waiting for Ollama')
    parser.add_argument('--ollama-timeout', type=float, default=30.0, help='Ollama readiness timeout (seconds)')
    
    args = parser.parse_args()
    
    # Handle Ollama wait flag
    wait_for_ollama = args.wait_for_ollama and not args.no_wait_ollama
    
    # Create configuration
    config = AgentConfig(
        camera_index=args.camera,
        rock64_host=args.rock64_host,
        rock64_port=args.rock64_port,
        ssh_key=args.ssh_key,
        forward_speed=args.forward_speed,
        turn_speed=args.turn_speed,
        safe_distance=args.safe_distance,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        connection_timeout=args.connection_timeout,
        ollama_host=args.ollama_host,
        ollama_port=args.ollama_port,
        wait_for_ollama=wait_for_ollama,
        ollama_timeout=args.ollama_timeout
    )
    
    # Create and run agent controller
    agent = AgentController(config)
    agent.run()


if __name__ == '__main__':
    main()
