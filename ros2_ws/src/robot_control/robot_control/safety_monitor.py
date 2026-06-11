#!/usr/bin/env python3
"""
safety_monitor.py — Multi-sensor fusion safety system for robot navigation.

Features:
- Ultrasonic distance monitoring
- Vision-based obstacle detection fusion
- Speed scaling based on distance
- Emergency stop trigger
- Safety status publishing
- Configurable safety thresholds

Usage:
  ros2 run robot_control safety_monitor
  ros2 run robot_control safety_monitor --ros-args -p safe_distance:=50
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int16, String
from geometry_msgs.msg import Twist


class SafetyMonitor(Node):
    """Multi-sensor fusion safety monitor node."""
    
    def __init__(self) -> None:
        super().__init__('safety_monitor')
        
        # --- Declare parameters ---
        self.declare_parameter('safe_distance', 50)  # cm
        self.declare_parameter('warning_distance', 100)  # cm
        self.declare_parameter('critical_distance', 20)  # cm
        self.declare_parameter('max_speed', 180)  # PWM
        self.declare_parameter('cautious_speed', 80)  # PWM
        self.declare_parameter('ultrasonic_topic', 'ultrasonic_distance')
        self.declare_parameter('vision_obstacle_topic', 'vision_obstacle')
        self.declare_parameter('cmd_vel_in_topic', 'cmd_vel_raw')
        self.declare_parameter('cmd_vel_out_topic', 'cmd_vel')
        self.declare_parameter('safety_status_topic', 'safety_status')
        self.declare_parameter('emergency_stop_topic', 'emergency_stop')
        
        # --- Get parameters ---
        self.safe_distance = self.get_parameter('safe_distance').value
        self.warning_distance = self.get_parameter('warning_distance').value
        self.critical_distance = self.get_parameter('critical_distance').value
        self.max_speed = self.get_parameter('max_speed').value
        self.cautious_speed = self.get_parameter('cautious_speed').value
        
        ultrasonic_topic = self.get_parameter('ultrasonic_topic').value
        vision_obstacle_topic = self.get_parameter('vision_obstacle_topic').value
        cmd_vel_in_topic = self.get_parameter('cmd_vel_in_topic').value
        cmd_vel_out_topic = self.get_parameter('cmd_vel_out_topic').value
        safety_status_topic = self.get_parameter('safety_status_topic').value
        emergency_stop_topic = self.get_parameter('emergency_stop_topic').value
        
        # --- Safety state ---
        self.ultrasonic_distance = 100  # cm
        self.vision_obstacle_detected = False
        self.vision_obstacle_direction = "none"
        self.emergency_stop_active = False
        self.speed_scale = 1.0
        
        # --- Create publishers ---
        self.cmd_vel_pub = self.create_publisher(Twist, cmd_vel_out_topic, 10)
        self.safety_status_pub = self.create_publisher(String, safety_status_topic, 10)
        self.emergency_stop_pub = self.create_publisher(String, emergency_stop_topic, 10)
        
        # --- Create subscriptions ---
        # Ultrasonic distance subscription
        self.create_subscription(
            Int16,
            ultrasonic_topic,
            self.ultrasonic_callback,
            QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        )
        
        # Vision obstacle subscription (optional)
        self.create_subscription(
            String,
            vision_obstacle_topic,
            self.vision_callback,
            10
        )
        
        # Raw cmd_vel subscription (for filtering)
        self.create_subscription(
            Twist,
            cmd_vel_in_topic,
            self.cmd_vel_callback,
            10
        )
        
        # --- Timer for safety status publishing ---
        self.status_timer = self.create_timer(1.0, self.publish_safety_status)
        
        self.get_logger().info('Safety Monitor initialized')
        self.get_logger().info(f'  Safe distance: {self.safe_distance} cm')
        self.get_logger().info(f'  Warning distance: {self.warning_distance} cm')
        self.get_logger().info(f'  Critical distance: {self.critical_distance} cm')
        self.get_logger().info(f'  Max speed: {self.max_speed}')
        self.get_logger().info(f'  Cautious speed: {self.cautious_speed}')
    
    def ultrasonic_callback(self, msg: Int16) -> None:
        """Handle ultrasonic distance updates."""
        self.ultrasonic_distance = msg.data
        self.update_safety_state()
    
    def vision_callback(self, msg: String) -> None:
        """Handle vision obstacle detection updates."""
        try:
            # Parse vision data: "detected,direction"
            parts = msg.data.split(',')
            if len(parts) >= 2:
                self.vision_obstacle_detected = (parts[0] == 'true')
                self.vision_obstacle_direction = parts[1]
            self.update_safety_state()
        except Exception as e:
            self.get_logger().warn(f'Failed to parse vision data: {e}')
    
    def update_safety_state(self) -> None:
        """Update safety state based on sensor fusion."""
        # Check for critical conditions
        if self.ultrasonic_distance < self.critical_distance:
            self.emergency_stop_active = True
            self.speed_scale = 0.0
            self.get_logger().warn(f'CRITICAL: Distance {self.ultrasonic_distance} cm < {self.critical_distance} cm')
            self.trigger_emergency_stop('ultrasonic_critical')
            return
        
        # Check for vision obstacle
        if self.vision_obstacle_detected and self.vision_obstacle_direction == 'center':
            self.emergency_stop_active = True
            self.speed_scale = 0.0
            self.get_logger().warn('CRITICAL: Vision obstacle detected ahead')
            self.trigger_emergency_stop('vision_obstacle')
            return
        
        # Calculate speed scale based on distance
        if self.ultrasonic_distance < self.safe_distance:
            # In safe zone, reduce speed significantly
            self.speed_scale = 0.3
            self.emergency_stop_active = False
        elif self.ultrasonic_distance < self.warning_distance:
            # In warning zone, reduce speed moderately
            self.speed_scale = 0.6
            self.emergency_stop_active = False
        else:
            # Clear, full speed
            self.speed_scale = 1.0
            self.emergency_stop_active = False
    
    def cmd_vel_callback(self, msg: Twist) -> None:
        """Filter and scale cmd_vel based on safety state."""
        # If emergency stop is active, don't forward commands
        if self.emergency_stop_active:
            self.get_logger().debug('Emergency stop active - blocking cmd_vel')
            return
        
        # Scale the velocity based on safety state
        scaled_msg = Twist()
        scaled_msg.linear.x = msg.linear.x * self.speed_scale
        scaled_msg.linear.y = msg.linear.y * self.speed_scale
        scaled_msg.linear.z = msg.linear.z * self.speed_scale
        scaled_msg.angular.x = msg.angular.x * self.speed_scale
        scaled_msg.angular.y = msg.angular.y * self.speed_scale
        scaled_msg.angular.z = msg.angular.z * self.speed_scale
        
        # Publish scaled command
        self.cmd_vel_pub.publish(scaled_msg)
    
    def trigger_emergency_stop(self, reason: str) -> None:
        """Trigger emergency stop and publish event."""
        msg = String()
        msg.data = f'EMERGENCY_STOP:{reason}'
        self.emergency_stop_pub.publish(msg)
        
        # Also publish zero velocity
        stop_msg = Twist()
        stop_msg.linear.x = 0.0
        stop_msg.angular.z = 0.0
        self.cmd_vel_pub.publish(stop_msg)
    
    def publish_safety_status(self) -> None:
        """Publish current safety status."""
        status = {
            'ultrasonic_distance': self.ultrasonic_distance,
            'vision_obstacle_detected': self.vision_obstacle_detected,
            'vision_obstacle_direction': self.vision_obstacle_direction,
            'emergency_stop_active': self.emergency_stop_active,
            'speed_scale': self.speed_scale,
            'safe_distance': self.safe_distance,
            'warning_distance': self.warning_distance,
        }
        
        msg = String()
        msg.data = str(status)
        self.safety_status_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SafetyMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
