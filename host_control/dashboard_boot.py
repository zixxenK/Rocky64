#!/usr/bin/env python3
"""
dashboard_boot.py — Boot orchestrator for unified robot dashboard.

This script manages the startup and shutdown of all robot subsystems:
- Serial connection to Arduino
- SSH connection to Rock64 (if needed)
- ROS2 launch (Linux only)
- Agent controller
- Camera stream
- Web dashboard

Usage:
  python host_control/dashboard_boot.py --start
  python host_control/dashboard_boot.py --stop
  python host_control/dashboard_boot.py --restart
  python host_control/dashboard_boot.py --status
  python host_control/dashboard_boot.py --daemon
"""

import argparse
import json
import os
import sys
import time
import subprocess
import signal
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

# Import platform utilities
from platform_utils import get_platform, get_default_serial_port, get_ssh_key_path


# --- CONFIGURATION ---
@dataclass
class BootConfig:
    platform: str = "auto"
    ros2_enabled: bool = True
    agent_enabled: bool = True
    camera_enabled: bool = True
    dashboard_enabled: bool = True
    ros2_workspace: str = ""
    ros2_launch_file: str = "rock64_bringup.launch.py"
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 5000
    serial_port: str = ""
    baud_rate: int = 115200
    rock64_host: str = "192.168.1.159"
    ssh_key: str = ""
    camera_source: str = "esp32"
    camera_url: str = "http://192.168.1.153/stream"
    camera_index: int = 0
    auto_boot: bool = True


# --- PROCESS MANAGER ---
class ProcessManager:
    """Manages subprocess lifecycle for robot services."""
    
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.config = BootConfig()
        self.running = False
        self.shutdown_requested = False
        
    def load_config(self, config_file: str = None) -> None:
        """Load boot configuration from file."""
        if config_file is None:
            config_file = os.path.join(os.path.dirname(__file__), "dashboard_config.json")
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(self.config, key):
                            setattr(self.config, key, value)
            
            # Set defaults if not configured
            if self.config.platform == "auto":
                self.config.platform = get_platform()
            if not self.config.serial_port:
                self.config.serial_port = get_default_serial_port()
            if not self.config.ssh_key:
                self.config.ssh_key = get_ssh_key_path()
            if not self.config.ros2_workspace and self.config.platform == "linux":
                # Try to detect ROS2 workspace
                self.config.ros2_workspace = os.path.expanduser("~/ros2_ws")
            
            print(f"[boot] Configuration loaded: platform={self.config.platform}")
        except Exception as e:
            print(f"[boot] Failed to load config: {e}")
    
    def save_config(self, config_file: str = None) -> None:
        """Save boot configuration to file."""
        if config_file is None:
            config_file = os.path.join(os.path.dirname(__file__), "dashboard_config.json")
        
        try:
            with open(config_file, 'w') as f:
                json.dump(asdict(self.config), f, indent=2)
            print(f"[boot] Configuration saved to {config_file}")
        except Exception as e:
            print(f"[boot] Failed to save config: {e}")
    
    def start_ros2(self) -> bool:
        """Start ROS2 launch (Linux only)."""
        if self.config.platform != "linux":
            print("[boot] ROS2 not available on this platform")
            return False
        
        if not self.config.ros2_enabled:
            print("[boot] ROS2 disabled in configuration")
            return False
        
        if not self.config.ros2_workspace:
            print("[boot] ROS2 workspace not configured")
            return False
        
        try:
            cmd = [
                "bash",
                "-c",
                f"cd {self.config.ros2_workspace} && "
                f"source install/setup.bash && "
                f"ros2 launch robot_bringup {self.config.ros2_launch_file}"
            ]
            
            print(f"[boot] Starting ROS2: {self.config.ros2_workspace}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes['ros2'] = process
            print(f"[boot] ROS2 started (PID: {process.pid})")
            return True
        except Exception as e:
            print(f"[boot] Failed to start ROS2: {e}")
            return False
    
    def start_agent(self) -> bool:
        """Start agent controller."""
        if not self.config.agent_enabled:
            print("[boot] Agent disabled in configuration")
            return False
        
        try:
            agent_script = os.path.join(os.path.dirname(__file__), "agent_controller.py")
            if not os.path.exists(agent_script):
                print(f"[boot] Agent script not found: {agent_script}")
                return False
            
            cmd = [
                sys.executable,
                agent_script,
                "--camera", str(self.config.camera_index),
                "--rock64-host", self.config.rock64_host,
                "--forward-speed", "120",
                "--turn-speed", "80",
            ]
            
            print("[boot] Starting agent controller")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes['agent'] = process
            print(f"[boot] Agent started (PID: {process.pid})")
            return True
        except Exception as e:
            print(f"[boot] Failed to start agent: {e}")
            return False
    
    def start_dashboard(self) -> bool:
        """Start unified dashboard."""
        if not self.config.dashboard_enabled:
            print("[boot] Dashboard disabled in configuration")
            return False
        
        try:
            dashboard_script = os.path.join(os.path.dirname(__file__), "unified_dashboard.py")
            if not os.path.exists(dashboard_script):
                print(f"[boot] Dashboard script not found: {dashboard_script}")
                return False
            
            cmd = [
                sys.executable,
                dashboard_script,
                "--host", self.config.dashboard_host,
                "--port", str(self.config.dashboard_port),
                "--serial-port", self.config.serial_port,
                "--baud", str(self.config.baud_rate),
            ]
            
            if self.config.auto_boot:
                cmd.append("--boot-all")
            
            print(f"[boot] Starting dashboard on {self.config.dashboard_host}:{self.config.dashboard_port}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes['dashboard'] = process
            print(f"[boot] Dashboard started (PID: {process.pid})")
            return True
        except Exception as e:
            print(f"[boot] Failed to start dashboard: {e}")
            return False
    
    def stop_process(self, name: str) -> bool:
        """Stop a specific process."""
        if name not in self.processes:
            print(f"[boot] Process {name} not running")
            return False
        
        try:
            process = self.processes[name]
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"[boot] Process {name} did not terminate gracefully, killing")
                process.kill()
                process.wait()
            
            del self.processes[name]
            print(f"[boot] Process {name} stopped")
            return True
        except Exception as e:
            print(f"[boot] Failed to stop process {name}: {e}")
            return False
    
    def stop_all(self) -> None:
        """Stop all processes in reverse order."""
        print("[boot] Stopping all processes...")
        
        # Stop in reverse order: dashboard -> agent -> ros2
        for name in ['dashboard', 'agent', 'ros2']:
            if name in self.processes:
                self.stop_process(name)
        
        print("[boot] All processes stopped")
    
    def start_all(self) -> bool:
        """Start all processes in correct order."""
        print("[boot] Starting all processes...")
        print(f"[boot] Platform: {self.config.platform}")
        
        success = True
        
        # Step 1: Start ROS2 (Linux only)
        if self.config.platform == "linux":
            if not self.start_ros2():
                print("[boot] WARNING: ROS2 failed to start")
                success = False
            time.sleep(2)  # Give ROS2 time to initialize
        
        # Step 2: Start agent
        if not self.start_agent():
            print("[boot] WARNING: Agent failed to start")
            success = False
        time.sleep(1)
        
        # Step 3: Start dashboard
        if not self.start_dashboard():
            print("[boot] ERROR: Dashboard failed to start")
            success = False
        
        if success:
            print("[boot] All processes started successfully")
        else:
            print("[boot] Some processes failed to start")
        
        return success
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all processes."""
        status = {
            'platform': self.config.platform,
            'processes': {},
            'overall': 'running' if self.processes else 'stopped'
        }
        
        for name, process in self.processes.items():
            if process.poll() is None:
                status['processes'][name] = {
                    'pid': process.pid,
                    'status': 'running'
                }
            else:
                status['processes'][name] = {
                    'pid': process.pid,
                    'status': 'stopped',
                    'returncode': process.returncode
                }
        
        return status
    
    def monitor(self) -> None:
        """Monitor processes and restart if needed."""
        print("[boot] Starting process monitor...")
        
        while self.running and not self.shutdown_requested:
            for name, process in list(self.processes.items()):
                if process.poll() is not None:
                    print(f"[boot] Process {name} died (exit code: {process.returncode})")
                    
                    # Restart if not shutdown requested
                    if not self.shutdown_requested:
                        print(f"[boot] Attempting to restart {name}...")
                        if name == 'ros2':
                            self.start_ros2()
                        elif name == 'agent':
                            self.start_agent()
                        elif name == 'dashboard':
                            self.start_dashboard()
            
            time.sleep(2)
        
        print("[boot] Process monitor stopped")
    
    def run_daemon(self) -> None:
        """Run as daemon with monitoring."""
        self.running = True
        
        # Setup signal handlers
        def signal_handler(signum, frame):
            print(f"[boot] Received signal {signum}")
            self.shutdown_requested = True
            self.stop_all()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start all processes
        self.start_all()
        
        # Start monitor thread
        monitor_thread = threading.Thread(target=self.monitor, daemon=True)
        monitor_thread.start()
        
        # Keep main thread alive
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[boot] Received interrupt")
            self.shutdown_requested = True
            self.stop_all()


# --- MAIN ---
def main():
    parser = argparse.ArgumentParser(
        description="Boot orchestrator for unified robot dashboard"
    )
    parser.add_argument('--start', action='store_true', help='Start all services')
    parser.add_argument('--stop', action='store_true', help='Stop all services')
    parser.add_argument('--restart', action='store_true', help='Restart all services')
    parser.add_argument('--status', action='store_true', help='Show status of all services')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon with monitoring')
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--ros2-workspace', help='ROS2 workspace path')
    parser.add_argument('--dashboard-port', type=int, help='Dashboard port')
    parser.add_argument('--no-ros2', action='store_true', help='Disable ROS2')
    parser.add_argument('--no-agent', action='store_true', help='Disable agent')
    
    args = parser.parse_args()
    
    manager = ProcessManager()
    manager.load_config(args.config)
    
    # Apply command-line overrides
    if args.ros2_workspace:
        manager.config.ros2_workspace = args.ros2_workspace
    if args.dashboard_port:
        manager.config.dashboard_port = args.dashboard_port
    if args.no_ros2:
        manager.config.ros2_enabled = False
    if args.no_agent:
        manager.config.agent_enabled = False
    
    # Execute command
    if args.status:
        status = manager.get_status()
        print(json.dumps(status, indent=2))
        return
    
    if args.stop:
        manager.stop_all()
        return
    
    if args.restart:
        manager.stop_all()
        time.sleep(2)
        manager.start_all()
        return
    
    if args.daemon:
        manager.run_daemon()
        return
    
    if args.start:
        manager.start_all()
        return
    
    # Default: show help
    parser.print_help()


if __name__ == '__main__':
    main()
