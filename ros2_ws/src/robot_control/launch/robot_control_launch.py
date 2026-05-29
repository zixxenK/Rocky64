from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='robot_control',
            executable='robot_control_node',
            name='robot_control_node',
            output='screen',
            parameters=[
                {'serial_port': '/dev/ttyS1'},
                {'baudrate': 115200},
                {'camera_ip': '192.168.4.1'},
                {'camera_port': 80},
            ],
        ),
    ])
