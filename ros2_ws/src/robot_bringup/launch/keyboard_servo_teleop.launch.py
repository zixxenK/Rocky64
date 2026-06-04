from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    robot_namespace = LaunchConfiguration('robot_namespace')
    cmd_vel_topic = LaunchConfiguration('cmd_vel_topic')
    camera_servo_topic = LaunchConfiguration('camera_servo_topic')
    linear_speed = LaunchConfiguration('linear_speed')
    angular_speed = LaunchConfiguration('angular_speed')
    publish_rate = LaunchConfiguration('publish_rate')
    servo_step = LaunchConfiguration('servo_step')
    servo_repeat_hz = LaunchConfiguration('servo_repeat_hz')

    return LaunchDescription([
        DeclareLaunchArgument('robot_namespace', default_value='rock64_1'),
        DeclareLaunchArgument('cmd_vel_topic', default_value='cmd_vel'),
        DeclareLaunchArgument(
            'camera_servo_topic',
            default_value='camera_servo',
        ),
        DeclareLaunchArgument('linear_speed', default_value='0.6'),
        DeclareLaunchArgument('angular_speed', default_value='1.0'),
        DeclareLaunchArgument('publish_rate', default_value='20.0'),
        DeclareLaunchArgument('servo_step', default_value='5'),
        DeclareLaunchArgument('servo_repeat_hz', default_value='8.0'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('robot_control'),
                    'launch',
                    'keyboard_servo_teleop.launch.py',
                ])
            ),
            launch_arguments={
                'robot_namespace': robot_namespace,
                'cmd_vel_topic': cmd_vel_topic,
                'camera_servo_topic': camera_servo_topic,
                'linear_speed': linear_speed,
                'angular_speed': angular_speed,
                'publish_rate': publish_rate,
                'servo_step': servo_step,
                'servo_repeat_hz': servo_repeat_hz,
            }.items(),
        ),
    ])
