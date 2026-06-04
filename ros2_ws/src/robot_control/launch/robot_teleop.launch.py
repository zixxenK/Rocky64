from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    # 1. Declare a flexible command-line argument for the IP
    robot_ip_arg = DeclareLaunchArgument(
        'robot_ip',
        default_value='192.168.1.159',  # Falls back to this if you don't type one
        description='IP address of the robot micro-controller'
    )

    return LaunchDescription([
        robot_ip_arg,

        # Start the PS5 Controller Bridge
        Node(
            package='robot_control',
            executable='ps5_ros_bridge',
            name='ps5_ros_bridge',
            output='screen'
        ),
        
        # Start the Wireless UDP Bridge to the Robot
        Node(
            package='robot_control',
            executable='udp_robot_bridge',
            name='udp_robot_bridge',
            output='screen',
            parameters=[
                {'robot_ip': LaunchConfiguration('robot_ip')}  # Reads the argument dynamically
            ]
        )
    ])