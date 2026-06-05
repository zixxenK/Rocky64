from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    robot_namespace = LaunchConfiguration('robot_namespace')
    serial_port = LaunchConfiguration('serial_port')
    baud_rate = LaunchConfiguration('baud_rate')
    camera_url = LaunchConfiguration('camera_url')
    camera_topic = LaunchConfiguration('camera_topic')
    frame_id = LaunchConfiguration('frame_id')
    publish_rate = LaunchConfiguration('publish_rate')
    cmd_vel_topic = LaunchConfiguration('cmd_vel_topic')
    camera_servo_topic = LaunchConfiguration('camera_servo_topic')
    telemetry_topic = LaunchConfiguration('telemetry_topic')
    params_file = LaunchConfiguration('params_file')

    default_params_file = PathJoinSubstitution([
        FindPackageShare('robot_control'), 'config', 'rock64_hardware.yaml'
    ])

    return LaunchDescription([
        DeclareLaunchArgument('robot_namespace', default_value='rock64_1'),
        DeclareLaunchArgument('serial_port', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('baud_rate', default_value='115200'),
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
            'params_file',
            default_value=default_params_file,
            description=(
                'Absolute path to the robot_control parameter YAML file.'
            ),
        ),
        Node(
            package='robot_control',
            executable='arduino_serial_bridge',
            namespace=robot_namespace,
            name='arduino_serial_bridge',
            output='screen',
            parameters=[
                params_file,
                {'serial_port': serial_port},
                {'baud_rate': baud_rate},
                {'cmd_vel_topic': cmd_vel_topic},
                {'camera_servo_topic': camera_servo_topic},
                {'telemetry_topic': telemetry_topic},
            ],
        ),
        Node(
            package='robot_control',
            executable='esp32_camera_bridge',
            namespace=robot_namespace,
            name='esp32_camera_bridge',
            output='screen',
            parameters=[
                params_file,
                {'camera_url': camera_url},
                {'camera_topic': camera_topic},
                {'frame_id': frame_id},
                {'publish_rate': publish_rate},
            ],
        ),
    ])
