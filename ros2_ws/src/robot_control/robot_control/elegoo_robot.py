"""elegoo_robot.py — Concrete HAL implementation for Elegoo robot platform.

This module implements the AbstractRobot interface for the Elegoo robot hardware,
using serial communication with the Arduino firmware.

Protocol:
- Baud rate: 115200
- Command format: <ID,DIR,SPEED>\n
  - ID: Motor ID (1 = Right, 2 = Left)
  - DIR: Direction (F = Forward, B = Backward, S = Stop)
  - SPEED: PWM value (0-255)

Usage:
    from elegoo_robot import ElegooSerialRobot
    
    robot = ElegooSerialRobot(port='/dev/ttyUSB0')
    robot.move(linear=0.5, angular=0.0)
    sensor_data = robot.get_sensor_data()
    robot.stop()
"""

import serial
import time
import logging
from typing import Dict, Any, Optional

from robot_hal import AbstractRobot


class ElegooSerialRobot(AbstractRobot):
    """Concrete implementation of AbstractRobot for Elegoo hardware.
    
    This class handles the specific serial protocol requirements for the Elegoo
    robot platform, including differential drive kinematics and sensor data parsing.
    """
    
    def __init__(self, port: str = '/dev/ttyUSB0', baud: int = 115200, timeout: float = 0.1):
        """Initialize the Elegoo robot connection.
        
        Args:
            port: Serial port device path (e.g., '/dev/ttyUSB0' or 'COM3' on Windows)
            baud: Baud rate for serial communication (default: 115200)
            timeout: Serial read timeout in seconds (default: 0.1)
        """
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None
        self.logger = logging.getLogger("ElegooHAL")
        
        # Differential drive parameters
        self.wheel_base = 0.15  # Distance between wheels in meters
        self.wheel_radius = 0.03  # Wheel radius in meters
        self.max_speed = 255  # Maximum PWM value
        
        # Sensor cache
        self._sensor_cache: Dict[str, Any] = {
            'ultrasonic_distance': 100.0,
            'battery_voltage': 12.0,
        }
        
        # Connect to hardware
        self._connect()
    
    def _connect(self) -> bool:
        """Establish serial connection to Arduino."""
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
            # Allow time for Arduino bootloader to reset
            time.sleep(2)
            self.ser.reset_input_buffer()
            self.logger.info(f"Connected to Elegoo robot on {self.port} @ {self.baud} baud")
            return True
        except serial.SerialException as e:
            self.logger.error(f"Serial connection failed: {e}")
            self.logger.error("Hint: Ensure user is in dialout group: sudo usermod -a -G dialout $USER")
            self.ser = None
            return False
    
    def _send_packet(self, motor_id: int, direction: str, speed: int) -> None:
        """Send formatted packet to Arduino.
        
        Args:
            motor_id: Motor ID (1 = Right, 2 = Left)
            direction: Direction ('F' = Forward, 'B' = Backward, 'S' = Stop)
            speed: PWM value (0-255)
        """
        if self.ser is None or not self.ser.is_open:
            self.logger.warning("Cannot send packet: not connected")
            return
        
        # Clamp speed to valid range
        speed = max(0, min(self.max_speed, int(speed)))
        
        # Format: <ID,DIR,SPEED>\n
        packet = f"<{motor_id},{direction},{speed}>\n"
        
        try:
            self.ser.write(packet.encode('utf-8'))
            self.ser.flush()
        except serial.SerialException as e:
            self.logger.error(f"Serial write failure: {e}")
    
    def _twist_to_wheel_speeds(self, linear: float, angular: float) -> tuple[int, int]:
        """Convert Twist velocities to wheel speeds (differential drive kinematics).
        
        Args:
            linear: Linear velocity (-1.0 to 1.0)
            angular: Angular velocity (-1.0 to 1.0)
        
        Returns:
            Tuple of (right_speed, left_speed) as PWM values (0-255)
        """
        # Clamp inputs
        linear = max(-1.0, min(1.0, linear))
        angular = max(-1.0, min(1.0, angular))
        
        # Differential drive kinematics
        # v_right = v_linear + (angular * wheel_base / 2)
        # v_left = v_linear - (angular * wheel_base / 2)
        
        right_vel = linear + (angular * 0.5)
        left_vel = linear - (angular * 0.5)
        
        # Convert to PWM (0-255)
        right_pwm = int(abs(right_vel) * self.max_speed)
        left_pwm = int(abs(left_vel) * self.max_speed)
        
        return right_pwm, left_pwm
    
    def move(self, linear: float, angular: float) -> None:
        """Translate velocity commands into hardware movement.
        
        Args:
            linear: Linear velocity (-1.0 to 1.0, where 1.0 = max forward speed)
            angular: Angular velocity (-1.0 to 1.0, where 1.0 = max clockwise turn)
        """
        if self.ser is None or not self.ser.is_open:
            self.logger.warning("Cannot move: not connected")
            return
        
        # Convert to wheel speeds
        right_speed, left_speed = self._twist_to_wheel_speeds(linear, angular)
        
        # Determine directions
        right_dir = 'F' if linear + angular >= 0 else 'B'
        left_dir = 'F' if linear - angular >= 0 else 'B'
        
        # Send motor commands
        # Motor 1 = Right wheel, Motor 2 = Left wheel (matches firmware pinout)
        self._send_packet(1, right_dir, right_speed)
        self._send_packet(2, left_dir, left_speed)
        
        self.logger.debug(f"Move: linear={linear:.2f}, angular={angular:.2f} -> R:{right_speed} L:{left_speed}")
    
    def get_sensor_data(self) -> Dict[str, Any]:
        """Return a dictionary of all sensor readings.
        
        Returns:
            Dictionary containing sensor data from the Arduino.
        """
        if self.ser is None or not self.ser.is_open:
            return self._sensor_cache
        
        try:
            # Request sensor data from Arduino
            self.ser.write(b"<GET_SENSORS>\n")
            self.ser.flush()
            
            # Read response (timeout handled by serial timeout)
            response = self.ser.readline().decode('utf-8', errors='replace').strip()
            
            if response:
                # Parse response format: 'DIST:0.25,BATT:12.5'
                for item in response.split(','):
                    if ':' in item:
                        key, value = item.split(':', 1)
                        try:
                            self._sensor_cache[key.lower()] = float(value)
                        except ValueError:
                            self.logger.warning(f"Failed to parse sensor value: {item}")
            
            return self._sensor_cache.copy()
            
        except serial.SerialException as e:
            self.logger.error(f"Sensor read error: {e}")
            return self._sensor_cache.copy()
    
    def stop(self) -> None:
        """Immediate safety stop."""
        if self.ser is None or not self.ser.is_open:
            return
        
        # Send stop commands to both motors
        self._send_packet(1, 'S', 0)
        self._send_packet(2, 'S', 0)
        self.logger.info("Emergency stop executed")
    
    def is_connected(self) -> bool:
        """Check if the robot hardware is connected and responsive."""
        return self.ser is not None and self.ser.is_open
    
    def disconnect(self) -> None:
        """Cleanly disconnect from the robot hardware."""
        self.stop()
        
        if self.ser is not None and self.ser.is_open:
            try:
                self.ser.close()
                self.logger.info(f"Disconnected from {self.port}")
            except serial.SerialException as e:
                self.logger.error(f"Disconnect error: {e}")
        
        self.ser = None
