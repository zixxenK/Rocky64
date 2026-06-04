from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    robot_namespace = LaunchConfiguration('robot_namespace')
    cmd_vel_topic = LaunchConfiguration('cmd_vel_topic')

    return LaunchDescription([
        DeclareLaunchArgument('robot_namespace', default_value='rock64_1'),
        DeclareLaunchArgument('cmd_vel_topic', default_value='cmd_vel'),
        Node(
            package='teleop_twist_keyboard',
            executable='teleop_twist_keyboard',
            namespace=robot_namespace,
            name='keyboard_teleop',
            output='screen',
            remappings=[('cmd_vel', cmd_vel_topic)],
        ),
    ])