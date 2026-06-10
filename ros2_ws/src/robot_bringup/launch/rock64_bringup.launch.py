from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    LaunchConfiguration,
    PathJoinSubstitution,
    PythonExpression,
)
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    robot_namespace = LaunchConfiguration('robot_namespace')
    serial_port = LaunchConfiguration('serial_port')
    baud_rate = LaunchConfiguration('baud_rate')
    legacy_baudrate = LaunchConfiguration('baudrate')
    camera_url = LaunchConfiguration('camera_url')
    camera_topic = LaunchConfiguration('camera_topic')
    frame_id = LaunchConfiguration('frame_id')
    publish_rate = LaunchConfiguration('publish_rate')
    cmd_vel_topic = LaunchConfiguration('cmd_vel_topic')
    camera_servo_topic = LaunchConfiguration('camera_servo_topic')
    telemetry_topic = LaunchConfiguration('telemetry_topic')
    ultrasonic_distance_topic = LaunchConfiguration('ultrasonic_distance_topic')
    params_file = LaunchConfiguration('params_file')

    default_params_file = PathJoinSubstitution([
        FindPackageShare('robot_control'), 'config', 'rock64_hardware.yaml'
    ])
    effective_baud_rate = PythonExpression([
        "'",
        legacy_baudrate,
        "' if '",
        legacy_baudrate,
        "' else '",
        baud_rate,
        "'",
    ])

    return LaunchDescription([
        DeclareLaunchArgument('robot_namespace', default_value='rock64_1'),
        DeclareLaunchArgument('serial_port', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('baud_rate', default_value='115200'),
        DeclareLaunchArgument('baudrate', default_value=''),
        DeclareLaunchArgument(
            'camera_url', default_value='http://192.168.1.153/stream'
        ),
        DeclareLaunchArgument(
            'camera_topic', default_value='camera/image_raw'
        ),
        DeclareLaunchArgument('frame_id', default_value='camera'),
        DeclareLaunchArgument('publish_rate', default_value='10.0'),
        DeclareLaunchArgument('cmd_vel_topic', default_value='cmd_vel'),
        DeclareLaunchArgument(
            'camera_servo_topic', default_value='camera_servo'
        ),
        DeclareLaunchArgument(
            'telemetry_topic', default_value='robot_telemetry'
        ),
        DeclareLaunchArgument(
            'ultrasonic_distance_topic', default_value='ultrasonic_distance'
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params_file,
            description=(
                'Absolute path to the robot_control parameter YAML file.'
            ),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('robot_control'),
                    'launch',
                    'rock64_hardware.launch.py',
                ])
            ),
            launch_arguments={
                'robot_namespace': robot_namespace,
                'serial_port': serial_port,
                'baud_rate': effective_baud_rate,
                'camera_url': camera_url,
                'camera_topic': camera_topic,
                'frame_id': frame_id,
                'publish_rate': publish_rate,
                'cmd_vel_topic': cmd_vel_topic,
                'camera_servo_topic': camera_servo_topic,
                'telemetry_topic': telemetry_topic,
                'ultrasonic_distance_topic': ultrasonic_distance_topic,
                'params_file': params_file,
            }.items(),
        ),
    ])
