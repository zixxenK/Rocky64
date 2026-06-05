import serial
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Int16

# Ensure you have installed pyserial: pip install pyserial
class SerialRobotBridge(Node):
    def __init__(self):
        super().__init__('serial_robot_bridge')
        
        # Adjust port to match your output from 'ls /dev/tty*'
        self.port = self.declare_parameter('port', '/dev/ttyUSB0').value
        self.baudrate = 115200
        self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        
        self.create_subscription(Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        self.get_logger().info(f'Serial Bridge connected to {self.port}')

    def cmd_vel_callback(self, msg: Twist) -> None:
        # Your existing mapping logic
        from robot_control.control_mapping import twist_to_wheel_speeds, motor_packet
        left, right = twist_to_wheel_speeds(msg.linear.x, msg.angular.z)
        
        # Send packets directly to Arduino
        self.ser.write(motor_packet(1, right).encode('utf-8'))
        self.ser.write(motor_packet(2, left).encode('utf-8'))

def main(args=None):
    rclpy.init(args=args)
    node = SerialRobotBridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
