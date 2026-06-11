#!/usr/bin/env python3
"""
safety_watchdog.py — AI command gatekeeper with ultrasonic safety validation.

This node implements a safety-first gatekeeper pattern where AI commands flow
through validation layers before reaching motors. It intercepts commands from
/cmd_vel_ai and only forwards them to /cmd_vel if the ultrasonic sensor
indicates a safe path.

Features:
- Subscribes to ultrasonic_distance (std_msgs/msg/Int16) for obstacle detection
- Subscribes to /cmd_vel_ai (geometry_msgs/msg/Twist) for AI-generated commands
- Publishes to /cmd_vel (geometry_msgs/msg/Twist) for motor control
- Blocks forward movement if obstacle within 15cm
- Emergency stop on safety violations
- ROS 2 logging for safety events

Usage:
  ros2 run robot_control safety_watchdog
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int16


class SafetyWatchdog(Node):
    """Safety watchdog node that validates AI commands against sensor data."""
    
    def __init__(self) -> None:
        super().__init__('safety_watchdog')
        
        # Safety threshold in centimeters (15 cm)
        self.min_safe_distance = 15
        # Current distance reading from ultrasonic sensor (default to safe)
        self.current_distance = 999
        
        # --- Create subscriptions ---
        # Subscribe to ultrasonic distance sensor (Int16 in cm)
        self.sensor_sub = self.create_subscription(
            Int16,
            'ultrasonic_distance',
            self.sensor_callback,
            10
        )
        
        # Subscribe to AI-generated movement commands
        self.ai_cmd_sub = self.create_subscription(
            Twist,
            '/cmd_vel_ai',
            self.ai_cmd_callback,
            10
        )
        
        # --- Create publishers ---
        # Publish validated commands to actual motor controller
        self.motor_pub = self.create_publisher(
            Twist,
            '/cmd_vel',
            10
        )
        
        self.get_logger().info('Safety Watchdog initialized')
        self.get_logger().info(f'  Minimum safe distance: {self.min_safe_distance} cm')
        self.get_logger().info('  Subscribing to: ultrasonic_distance, /cmd_vel_ai')
        self.get_logger().info('  Publishing to: /cmd_vel')
    
    def sensor_callback(self, msg: Int16) -> None:
        """
        Updates the current distance from the ultrasonic sensor.
        
        Args:
            msg: std_msgs/msg/Int16 message containing distance in centimeters
        """
        self.current_distance = msg.data
        
        # Log if we suddenly detect an obstacle within critical range
        if self.current_distance < self.min_safe_distance:
            self.get_logger().warn(
                f'OBSTACLE DETECTED: Distance {self.current_distance} cm < {self.min_safe_distance} cm'
            )
    
    def ai_cmd_callback(self, msg: Twist) -> None:
        """
        Intercepts AI commands and validates them against physical sensor data.
        
        Args:
            msg: geometry_msgs/msg/Twist message from AI agent
        """
        # Check if the AI is attempting to drive forward
        driving_forward = msg.linear.x > 0.0
        
        if driving_forward and self.current_distance < self.min_safe_distance:
            # BLOCK: AI attempting to drive into obstacle
            self.force_stop(
                f"BLOCKED: AI attempted to drive forward at {self.current_distance} cm "
                f"(threshold: {self.min_safe_distance} cm)"
            )
        else:
            # SAFE: Pass the AI's command directly to motors
            self.motor_pub.publish(msg)
    
    def force_stop(self, reason: str) -> None:
        """
        Publishes a zero-velocity emergency stop command to the motors.
        
        Args:
            reason: Human-readable explanation for the safety intervention
        """
        stop_msg = Twist()
        stop_msg.linear.x = 0.0
        stop_msg.linear.y = 0.0
        stop_msg.linear.z = 0.0
        stop_msg.angular.x = 0.0
        stop_msg.angular.y = 0.0
        stop_msg.angular.z = 0.0
        
        self.motor_pub.publish(stop_msg)
        self.get_logger().warn(f'SAFETY INTERVENTION: {reason}')


def main(args=None) -> None:
    """Main entry point for the safety watchdog node."""
    rclpy.init(args=args)
    watchdog = SafetyWatchdog()
    
    try:
        rclpy.spin(watchdog)
    except KeyboardInterrupt:
        pass
    finally:
        watchdog.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
