"""robot_factory.py — Factory pattern for dynamic robot instantiation.

This module provides the RobotFactory class which dynamically instantiates robot
implementations based on configuration files. This allows switching between
different hardware platforms (Elegoo, Simulation, etc.) without changing code.

Usage:
    from robot_factory import RobotFactory
    
    robot = RobotFactory.get_robot('config/robot_registry.yaml')
    robot.move(linear=0.5, angular=0.0)
"""

import importlib
import logging
import os
from typing import Optional

import yaml

from robot_hal import AbstractRobot


class RobotFactory:
    """Factory for dynamically instantiating robot implementations.
    
    This class reads a YAML configuration file and instantiates the appropriate
    robot class based on the active_robot setting. This enables easy switching
    between hardware platforms without code changes.
    """
    
    @staticmethod
    def get_robot(config_path: str) -> AbstractRobot:
        """Instantiate a robot based on configuration file.
        
        Args:
            config_path: Path to the robot_registry.yaml configuration file
        
        Returns:
            An instance of the configured robot class (implements AbstractRobot)
        
        Raises:
            FileNotFoundError: If config file doesn't exist
            KeyError: If required configuration keys are missing
            ImportError: If robot module cannot be imported
            AttributeError: If robot class doesn't exist in module
        """
        logger = logging.getLogger("RobotFactory")
        
        # Resolve config path relative to this file if not absolute
        if not os.path.isabs(config_path):
            # Assume config is in the config directory relative to this module
            module_dir = os.path.dirname(__file__)
            config_dir = os.path.join(os.path.dirname(module_dir), 'config')
            config_path = os.path.join(config_dir, config_path)
        
        # Load configuration
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Robot config not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Get active robot configuration
        active_robot = config.get('active_robot')
        if not active_robot:
            raise KeyError("Missing 'active_robot' key in configuration")
        
        robots_config = config.get('robots', {})
        if active_robot not in robots_config:
            raise KeyError(f"Robot '{active_robot}' not found in robots configuration")
        
        robot_cfg = robots_config[active_robot]
        
        # Extract class and module information
        class_name = robot_cfg.get('class_name')
        module_path = robot_cfg.get('module_path')
        
        if not class_name or not module_path:
            raise KeyError(f"Missing 'class_name' or 'module_path' for robot '{active_robot}'")
        
        logger.info(f"Instantiating robot: {active_robot} ({class_name} from {module_path})")
        
        # Dynamically import the module
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(f"Failed to import module '{module_path}': {e}")
        
        # Get the robot class
        try:
            robot_class = getattr(module, class_name)
        except AttributeError as e:
            raise AttributeError(f"Class '{class_name}' not found in module '{module_path}': {e}")
        
        # Prepare constructor arguments (exclude class_name, module_path, description)
        constructor_args = {k: v for k, v in robot_cfg.items() 
                           if k not in ['class_name', 'module_path', 'description']}
        
        # Instantiate the robot
        try:
            robot = robot_class(**constructor_args)
            logger.info(f"Successfully instantiated {class_name}")
            return robot
        except Exception as e:
            raise RuntimeError(f"Failed to instantiate {class_name}: {e}")
    
    @staticmethod
    def list_available_robots(config_path: str) -> dict:
        """List all available robot configurations.
        
        Args:
            config_path: Path to the robot_registry.yaml configuration file
        
        Returns:
            Dictionary of robot configurations
        """
        # Resolve config path
        if not os.path.isabs(config_path):
            module_dir = os.path.dirname(__file__)
            config_dir = os.path.join(os.path.dirname(module_dir), 'config')
            config_path = os.path.join(config_dir, config_path)
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        return config.get('robots', {})
