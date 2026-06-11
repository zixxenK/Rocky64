"""simulation_robot.py — Mock robot implementation for testing without hardware.

This module provides a simulation implementation of the AbstractRobot interface
for testing AI logic without requiring physical hardware. It simulates sensor
data and motor commands in memory.

Usage:
    from simulation_robot import SimulationRobot
    
    robot = SimulationRobot()
    robot.move(linear=0.5, angular=0.0)
    sensor_data = robot.get_sensor_data()
    robot.stop()
"""

import logging
import time
import random
from typing import Dict, Any

from robot_hal import AbstractRobot


class SimulationRobot(AbstractRobot):
    """Mock implementation of AbstractRobot for testing without hardware.
    
    This class simulates robot behavior in memory, allowing development and
    testing of AI logic without requiring physical hardware. It maintains
    simulated state for position, orientation, and sensor readings.
    """
    
    def __init__(self):
        """Initialize the simulation robot."""
        self.logger = logging.getLogger("SimulationHAL")
        
        # Simulated robot state
        self._x = 0.0  # Position x (meters)
        self._y = 0.0  # Position y (meters)
        self._theta = 0.0  # Orientation (radians)
        self._linear_vel = 0.0  # Current linear velocity
        self._angular_vel = 0.0  # Current angular velocity
        self._last_update = time.time()
        
        # Simulated sensor data
        self._sensor_data: Dict[str, Any] = {
            'ultrasonic_distance': 100.0,
            'battery_voltage': 12.0,
            'gyro_x': 0.0,
            'gyro_y': 0.0,
            'gyro_z': 0.0,
        }
        
        # Simulation parameters
        self._connected = True
        self._obstacle_distance = 2.0  # Default obstacle distance (meters)
        
        self.logger.info("Simulation robot initialized")
    
    def set_obstacle_distance(self, distance: float) -> None:
        """Set the simulated obstacle distance for testing.
        
        Args:
            distance: Distance to obstacle in meters
        """
        self._obstacle_distance = distance
        self.logger.info(f"Simulated obstacle distance set to {distance}m")
    
    def move(self, linear: float, angular: float) -> None:
        """Translate velocity commands into simulated movement.
        
        Args:
            linear: Linear velocity (-1.0 to 1.0)
            angular: Angular velocity (-1.0 to 1.0)
        """
        if not self._connected:
            self.logger.warning("Cannot move: not connected")
            return
        
        # Clamp inputs
        linear = max(-1.0, min(1.0, linear))
        angular = max(-1.0, min(1.0, angular))
        
        # Update velocity state
        self._linear_vel = linear
        self._angular_vel = angular
        
        # Simulate position update (simple kinematics)
        current_time = time.time()
        dt = current_time - self._last_update
        self._last_update = current_time
        
        # Update position based on velocities
        # x_dot = v * cos(theta)
        # y_dot = v * sin(theta)
        # theta_dot = omega
        
        # Scale velocities for simulation (max 0.5 m/s linear, 2.0 rad/s angular)
        v_sim = linear * 0.5
        omega_sim = angular * 2.0
        
        self._x += v_sim * time.cos(self._theta) * dt
        self._y += v_sim * time.sin(self._theta) * dt
        self._theta += omega_sim * dt
        
        # Normalize theta to [-pi, pi]
        self._theta = (self._theta + 3.14159) % (2 * 3.14159) - 3.14159
        
        # Update simulated sensor data based on position
        self._update_sensors()
        
        self.logger.debug(
            f"Move: linear={linear:.2f}, angular={angular:.2f} -> "
            f"pos=({self._x:.2f}, {self._y:.2f}, {self._theta:.2f})"
        )
    
    def _update_sensors(self) -> None:
        """Update simulated sensor readings based on robot state."""
        # Simulate ultrasonic distance with some noise
        noise = random.uniform(-0.05, 0.05)
        self._sensor_data['ultrasonic_distance'] = max(0.0, self._obstacle_distance + noise)
        
        # Simulate battery drain (slowly decreasing)
        self._sensor_data['battery_voltage'] = max(9.0, 12.0 - (time.time() % 3600) / 3600 * 3.0)
        
        # Simulate gyroscope readings based on angular velocity
        self._sensor_data['gyro_x'] = self._angular_vel * 2.0 + random.uniform(-0.01, 0.01)
        self._sensor_data['gyro_y'] = random.uniform(-0.01, 0.01)
        self._sensor_data['gyro_z'] = random.uniform(-0.01, 0.01)
    
    def get_sensor_data(self) -> Dict[str, Any]:
        """Return a dictionary of simulated sensor readings.
        
        Returns:
            Dictionary containing simulated sensor data.
        """
        self._update_sensors()
        return self._sensor_data.copy()
    
    def stop(self) -> None:
        """Immediate safety stop."""
        self._linear_vel = 0.0
        self._angular_vel = 0.0
        self.logger.info("Emergency stop executed")
    
    def is_connected(self) -> bool:
        """Check if the simulation robot is connected."""
        return self._connected
    
    def disconnect(self) -> None:
        """Cleanly disconnect from the simulation."""
        self.stop()
        self._connected = False
        self.logger.info("Simulation robot disconnected")
    
    def get_position(self) -> tuple[float, float, float]:
        """Get current simulated position.
        
        Returns:
            Tuple of (x, y, theta) in meters and radians
        """
        return (self._x, self._y, self._theta)
    
    def reset_position(self) -> None:
        """Reset simulated position to origin."""
        self._x = 0.0
        self._y = 0.0
        self._theta = 0.0
        self.logger.info("Position reset to origin")
