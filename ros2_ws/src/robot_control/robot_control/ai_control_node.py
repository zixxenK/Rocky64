"""ai_control_node.py — ROS 2 AI agent node with LM Studio integration.

This node implements an AI-driven robot controller that uses LM Studio (or any
OpenAI-compatible API) to make navigation decisions. It follows the HAL pattern
to remain hardware-agnostic and implements safety constraints.

Architecture:
- Subscribes to sensor topics (ultrasonic, battery, etc.)
- Sends sensor state to LLM for decision making
- Executes commands through HAL with safety clamping
- Publishes AI thinking and decisions for dashboard visibility

Usage:
    ros2 run robot_control ai_control_node
    ros2 run robot_control ai_control_node --ros-args -p lm_studio_url:=http://192.168.1.81:1234/v1
"""

import json
import logging
import time
from typing import Dict, Any, Optional

import rclpy
from rclpy.node import Node
from rclpy.publisher import Publisher
from rclpy.subscription import Subscription
from geometry_msgs.msg import Twist
from std_msgs.msg import String, Int16, Float32

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
    logging.warning("OpenAI library not installed. AI features will be disabled.")

from robot_factory import RobotFactory
from robot_hal import AbstractRobot


class AIAgentNode(Node):
    """ROS 2 node for AI-driven robot control using LM Studio."""
    
    def __init__(self):
        super().__init__('ai_agent_node')
        
        # Declare parameters
        self._declare_parameters()
        
        # Initialize logging
        self.logger = logging.getLogger("AIAgentNode")
        
        # Initialize robot HAL
        self.robot: Optional[AbstractRobot] = None
        self._init_robot()
        
        # Initialize LLM client
        self.lm_client: Optional[OpenAI] = None
        self._init_lm_client()
        
        # Sensor state
        self.sensor_state: Dict[str, Any] = {
            'ultrasonic_distance': 100.0,
            'battery_voltage': 12.0,
            'last_update': time.time(),
        }
        
        # AI state
        self.ai_thinking = "Initializing..."
        self.last_decision = {}
        self.decision_count = 0
        
        # Create ROS 2 interfaces
        self._create_subscriptions()
        self._create_publishers()
        
        # AI loop timer (don't run too fast - LLMs are slow)
        ai_loop_rate = self.get_parameter('ai_loop_rate').value
        self.ai_timer = self.create_timer(ai_loop_rate, self.ai_loop)
        
        self.get_logger().info("AI Agent Node initialized")
        self.get_logger().info(f"AI loop rate: {ai_loop_rate} Hz")
        self.get_logger().info(f"Robot: {self.robot.__class__.__name__ if self.robot else 'None'}")
    
    def _declare_parameters(self):
        """Declare ROS 2 parameters."""
        # Robot configuration
        self.declare_parameter('robot_config', 'config/robot_registry.yaml')
        
        # LM Studio configuration
        self.declare_parameter('lm_studio_url', 'http://192.168.1.81:1234/v1')
        self.declare_parameter('lm_studio_api_key', 'lm-studio')
        self.declare_parameter('lm_model', 'local-model')
        
        # AI loop configuration
        self.declare_parameter('ai_loop_rate', 0.5)  # Hz (0.5 = 2 seconds per decision)
        self.declare_parameter('enable_ai', True)
        
        # Safety parameters
        self.declare_parameter('max_linear_speed', 1.0)
        self.declare_parameter('max_angular_speed', 1.0)
        self.declare_parameter('emergency_stop_distance', 20.0)  # cm
        
        # Topic names
        self.declare_parameter('ultrasonic_topic', 'ultrasonic_distance')
        self.declare_parameter('battery_topic', 'battery_voltage')
        self.declare_parameter('ai_thinking_topic', 'ai/thinking')
        self.declare_parameter('ai_decision_topic', 'ai/decision')
        self.declare_parameter('cmd_vel_topic', 'cmd_vel')
    
    def _init_robot(self):
        """Initialize robot using factory pattern."""
        try:
            config_path = self.get_parameter('robot_config').value
            self.robot = RobotFactory.get_robot(config_path)
            self.get_logger().info(f"Robot initialized: {self.robot.__class__.__name__}")
        except Exception as e:
            self.get_logger().error(f"Failed to initialize robot: {e}")
            self.robot = None
    
    def _init_lm_client(self):
        """Initialize LM Studio client."""
        if OpenAI is None:
            self.get_logger().warn("OpenAI library not available - AI features disabled")
            return
        
        try:
            base_url = self.get_parameter('lm_studio_url').value
            api_key = self.get_parameter('lm_studio_api_key').value
            
            self.lm_client = OpenAI(base_url=base_url, api_key=api_key)
            self.get_logger().info(f"LM Studio client initialized: {base_url}")
        except Exception as e:
            self.get_logger().error(f"Failed to initialize LM Studio client: {e}")
            self.lm_client = None
    
    def _create_subscriptions(self):
        """Create ROS 2 subscriptions for sensor data."""
        ultrasonic_topic = self.get_parameter('ultrasonic_topic').value
        battery_topic = self.get_parameter('battery_topic').value
        
        self.create_subscription(Int16, ultrasonic_topic, self.ultrasonic_callback, 10)
        self.create_subscription(Float32, battery_topic, self.battery_callback, 10)
        
        self.get_logger().info(f"Subscribed to: {ultrasonic_topic}, {battery_topic}")
    
    def _create_publishers(self):
        """Create ROS 2 publishers for AI state and commands."""
        thinking_topic = self.get_parameter('ai_thinking_topic').value
        decision_topic = self.get_parameter('ai_decision_topic').value
        cmd_vel_topic = self.get_parameter('cmd_vel_topic').value
        
        self.thinking_pub: Publisher = self.create_publisher(String, thinking_topic, 10)
        self.decision_pub: Publisher = self.create_publisher(String, decision_topic, 10)
        self.cmd_vel_pub: Publisher = self.create_publisher(Twist, cmd_vel_topic, 10)
        
        self.get_logger().info(f"Publishing to: {thinking_topic}, {decision_topic}, {cmd_vel_topic}")
    
    def ultrasonic_callback(self, msg: Int16):
        """Handle ultrasonic distance updates."""
        self.sensor_state['ultrasonic_distance'] = msg.data
        self.sensor_state['last_update'] = time.time()
    
    def battery_callback(self, msg: Float32):
        """Handle battery voltage updates."""
        self.sensor_state['battery_voltage'] = msg.data
        self.sensor_state['last_update'] = time.time()
    
    def ai_loop(self):
        """Main AI decision loop."""
        if not self.get_parameter('enable_ai').value:
            return
        
        if self.robot is None:
            self.get_logger().warn("Robot not initialized - skipping AI loop")
            return
        
        # Emergency stop check
        emergency_distance = self.get_parameter('emergency_stop_distance').value
        if self.sensor_state['ultrasonic_distance'] < emergency_distance:
            self.get_logger().warn(f"Emergency stop: distance {self.sensor_state['ultrasonic_distance']} cm")
            self.robot.stop()
            self.ai_thinking = "EMERGENCY STOP - Obstacle too close"
            self._publish_ai_state()
            return
        
        # Get AI decision
        decision = self._get_ai_decision()
        
        if decision:
            self._execute_decision(decision)
            self.decision_count += 1
    
    def _get_ai_decision(self) -> Optional[Dict[str, Any]]:
        """Query LLM for navigation decision."""
        if self.lm_client is None:
            # Fallback to simple rule-based behavior
            return self._rule_based_decision()
        
        try:
            # Construct prompt with sensor data
            prompt = self._construct_prompt()
            
            # Update thinking state
            self.ai_thinking = f"Analyzing: distance={self.sensor_state['ultrasonic_distance']}cm, battery={self.sensor_state['battery_voltage']}V"
            self._publish_ai_state()
            
            # Query LLM
            model = self.get_parameter('lm_model').value
            response = self.lm_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a robot controller. Output ONLY valid JSON with this schema: "
                                   "{'command': 'move'|'stop'|'scan', 'params': {'linear': float, 'angular': float, 'duration': float}, 'reasoning': string}. "
                                   "linear and angular must be between -1.0 and 1.0. duration is in seconds."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            # Parse response
            content = response.choices[0].message.content.strip()
            self.ai_thinking = f"LLM Response: {content}"
            self._publish_ai_state()
            
            # Try to extract JSON from response
            try:
                # Handle markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                decision = json.loads(content)
                self.last_decision = decision
                return decision
            except json.JSONDecodeError as e:
                self.get_logger().error(f"Failed to parse LLM response: {e}")
                self.get_logger().error(f"Response was: {content}")
                return self._rule_based_decision()
                
        except Exception as e:
            self.get_logger().error(f"LLM query failed: {e}")
            return self._rule_based_decision()
    
    def _construct_prompt(self) -> str:
        """Construct prompt for LLM with current sensor state."""
        distance = self.sensor_state['ultrasonic_distance']
        battery = self.sensor_state['battery_voltage']
        
        prompt = (
            f"Current robot state:\n"
            f"- Ultrasonic distance: {distance} cm\n"
            f"- Battery voltage: {battery} V\n"
            f"\n"
            f"Rules:\n"
            f"- If distance < 30 cm, command must be 'stop'\n"
            f"- If distance < 50 cm, reduce speed (linear < 0.3)\n"
            f"- Normal operation: move forward with moderate speed\n"
            f"- Battery low (< 10V): prefer 'stop' or slow movement\n"
            f"\n"
            f"What should the robot do next?"
        )
        return prompt
    
    def _rule_based_decision(self) -> Dict[str, Any]:
        """Fallback rule-based decision when LLM is unavailable."""
        distance = self.sensor_state['ultrasonic_distance']
        
        if distance < 30:
            return {
                'command': 'stop',
                'params': {'linear': 0.0, 'angular': 0.0, 'duration': 0.0},
                'reasoning': 'Rule-based: Obstacle too close'
            }
        elif distance < 50:
            return {
                'command': 'move',
                'params': {'linear': 0.2, 'angular': 0.0, 'duration': 1.0},
                'reasoning': 'Rule-based: Cautious approach'
            }
        else:
            return {
                'command': 'move',
                'params': {'linear': 0.5, 'angular': 0.0, 'duration': 1.0},
                'reasoning': 'Rule-based: Normal forward movement'
            }
    
    def _execute_decision(self, decision: Dict[str, Any]):
        """Execute AI decision with safety constraints."""
        cmd = decision.get('command', 'stop')
        params = decision.get('params', {})
        reasoning = decision.get('reasoning', '')
        
        # Update thinking
        self.ai_thinking = f"Executing: {cmd} - {reasoning}"
        self._publish_ai_state()
        
        # Safety clamping
        max_linear = self.get_parameter('max_linear_speed').value
        max_angular = self.get_parameter('max_angular_speed').value
        
        linear = max(-max_linear, min(max_linear, params.get('linear', 0.0)))
        angular = max(-max_angular, min(max_angular, params.get('angular', 0.0)))
        
        # Execute command
        if cmd == 'move':
            self.robot.move(linear, angular)
            
            # Also publish to cmd_vel topic for compatibility
            twist = Twist()
            twist.linear.x = linear
            twist.angular.z = angular
            self.cmd_vel_pub.publish(twist)
            
        elif cmd == 'scan':
            # Turn in place for scanning
            self.robot.move(0.0, 0.5)
            
            twist = Twist()
            twist.linear.x = 0.0
            twist.angular.z = 0.5
            self.cmd_vel_pub.publish(twist)
            
        elif cmd == 'stop':
            self.robot.stop()
            
            twist = Twist()
            twist.linear.x = 0.0
            twist.angular.z = 0.0
            self.cmd_vel_pub.publish(twist)
            
        else:
            self.get_logger().warn(f"Unknown command: {cmd}")
            self.robot.stop()
    
    def _publish_ai_state(self):
        """Publish AI thinking and decision state."""
        # Publish thinking
        thinking_msg = String()
        thinking_msg.data = self.ai_thinking
        self.thinking_pub.publish(thinking_msg)
        
        # Publish decision
        decision_msg = String()
        decision_msg.data = json.dumps(self.last_decision)
        self.decision_pub.publish(decision_msg)
    
    def destroy_node(self):
        """Clean shutdown."""
        if self.robot:
            self.robot.stop()
            self.robot.disconnect()
        
        super().destroy_node()


def main(args=None):
    """Main entry point."""
    rclpy.init(args=args)
    
    node = AIAgentNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
