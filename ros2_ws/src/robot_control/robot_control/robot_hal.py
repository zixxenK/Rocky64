"""robot_hal.py — Hardware Abstraction Layer interface for robot control.

This module defines the abstract interface that all robot implementations must follow.
The HAL decouples high-level AI/decision logic from low-level hardware-specific code.

Usage:
    from robot_hal import AbstractRobot
    from elegoo_robot import ElegooSerialRobot
    
    robot = ElegooSerialRobot(port='/dev/ttyUSB0')
    robot.move(linear=0.5, angular=0.0)
    sensor_data = robot.get_sensor_data()
    robot.stop()
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class AbstractRobot(ABC):
    """Abstract base class defining the robot hardware interface.
    
    All robot implementations (Elegoo, Simulation, etc.) must inherit from this class
    and implement the abstract methods. This ensures consistent behavior across
    different hardware platforms.
    """
    
    @abstractmethod
    def move(self, linear: float, angular: float) -> None:
        """Translate velocity commands into hardware movement.
        
        Args:
            linear: Linear velocity (-1.0 to 1.0, where 1.0 = max forward speed)
            angular: Angular velocity (-1.0 to 1.0, where 1.0 = max clockwise turn)
        
        The implementation should convert these normalized velocities to the
        appropriate motor commands for the specific hardware (e.g., PWM values,
        differential drive kinematics, etc.).
        """
        pass
    
    @abstractmethod
    def get_sensor_data(self) -> Dict[str, Any]:
        """Return a dictionary of all sensor readings.
        
        Returns:
            Dictionary containing sensor data. Expected keys include:
            - 'ultrasonic_distance': Distance in cm (float)
            - 'battery_voltage': Battery level in volts (float, optional)
            - 'gyro_x', 'gyro_y', 'gyro_z': Angular rates (float, optional)
            - Any other hardware-specific sensor data
        
        The implementation should query the hardware for current sensor readings
        and return them in a standardized format.
        """
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Immediate safety stop.
        
        This method should halt all motors immediately, regardless of current
        state. It is used for emergency stops and safe shutdown.
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the robot hardware is connected and responsive.
        
        Returns:
            True if the robot is connected and ready to accept commands,
            False otherwise.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly disconnect from the robot hardware.
        
        This method should release any resources (serial ports, network connections,
        etc.) and put the hardware in a safe state before shutdown.
        """
        pass
