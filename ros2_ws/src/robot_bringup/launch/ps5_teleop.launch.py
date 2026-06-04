from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    robot_namespace = LaunchConfiguration('robot_namespace')
    cmd_vel_topic = LaunchConfiguration('cmd_vel_topic')
    camera_servo_topic = LaunchConfiguration('camera_servo_topic')
    joystick_index = LaunchConfiguration('joystick_index')
    controller_name = LaunchConfiguration('controller_name')
    poll_interval = LaunchConfiguration('poll_interval')
    leftx_axis = LaunchConfiguration('leftx_axis')
    lefty_axis = LaunchConfiguration('lefty_axis')
    rightx_axis = LaunchConfiguration('rightx_axis')
    l2_axis = LaunchConfiguration('l2_axis')
    r2_axis = LaunchConfiguration('r2_axis')

    return LaunchDescription([
        DeclareLaunchArgument('robot_namespace', default_value='rock64_1'),
        DeclareLaunchArgument('cmd_vel_topic', default_value='cmd_vel'),
        DeclareLaunchArgument(
            'camera_servo_topic',
            default_value='camera_servo',
        ),
        DeclareLaunchArgument('joystick_index', default_value='0'),
        DeclareLaunchArgument('controller_name', default_value=''),
        DeclareLaunchArgument('poll_interval', default_value='2.0'),
        DeclareLaunchArgument('leftx_axis', default_value='0'),
        DeclareLaunchArgument('lefty_axis', default_value='1'),
        DeclareLaunchArgument('rightx_axis', default_value='2'),
        DeclareLaunchArgument('l2_axis', default_value='4'),
        DeclareLaunchArgument('r2_axis', default_value='5'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('robot_control'),
                    'launch',
                    'ps5_teleop.launch.py',
                ])
            ),
            launch_arguments={
                'robot_namespace': robot_namespace,
                'cmd_vel_topic': cmd_vel_topic,
                'camera_servo_topic': camera_servo_topic,
                'joystick_index': joystick_index,
                'controller_name': controller_name,
                'poll_interval': poll_interval,
                'leftx_axis': leftx_axis,
                'lefty_axis': lefty_axis,
                'rightx_axis': rightx_axis,
                'l2_axis': l2_axis,
                'r2_axis': r2_axis,
            }.items(),
        ),
    ])
