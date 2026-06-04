from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    robot_namespace = LaunchConfiguration('robot_namespace')
    cmd_vel_topic = LaunchConfiguration('cmd_vel_topic')

    return LaunchDescription([
        DeclareLaunchArgument('robot_namespace', default_value='rock64_1'),
        DeclareLaunchArgument('cmd_vel_topic', default_value='cmd_vel'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('robot_control'),
                    'launch',
                    'keyboard_teleop.launch.py',
                ])
            ),
            launch_arguments={
                'robot_namespace': robot_namespace,
                'cmd_vel_topic': cmd_vel_topic,
            }.items(),
        ),
    ])