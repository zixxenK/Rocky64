from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.substitutions import PythonExpression
from launch_ros.substitutions import FindPackageShare


def mode_selected(teleop_mode, expected_mode):
    return IfCondition(
        PythonExpression([
            "'",
            teleop_mode,
            "' == '",
            expected_mode,
            "'",
        ])
    )


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
    include_hardware = LaunchConfiguration('include_hardware')
    teleop_mode = LaunchConfiguration('teleop_mode')
    joystick_index = LaunchConfiguration('joystick_index')
    controller_name = LaunchConfiguration('controller_name')
    poll_interval = LaunchConfiguration('poll_interval')
    leftx_axis = LaunchConfiguration('leftx_axis')
    lefty_axis = LaunchConfiguration('lefty_axis')
    rightx_axis = LaunchConfiguration('rightx_axis')
    l2_axis = LaunchConfiguration('l2_axis')
    r2_axis = LaunchConfiguration('r2_axis')
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
        DeclareLaunchArgument('include_hardware', default_value='true'),
        DeclareLaunchArgument('teleop_mode', default_value='keyboard_servo'),
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
                    FindPackageShare('robot_bringup'),
                    'launch',
                    'rock64_bringup.launch.py',
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
            }.items(),
            condition=IfCondition(include_hardware),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('robot_bringup'),
                    'launch',
                    'keyboard_teleop.launch.py',
                ])
            ),
            launch_arguments={
                'robot_namespace': robot_namespace,
                'cmd_vel_topic': cmd_vel_topic,
            }.items(),
            condition=mode_selected(teleop_mode, 'keyboard'),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('robot_bringup'),
                    'launch',
                    'keyboard_servo_teleop.launch.py',
                ])
            ),
            launch_arguments={
                'robot_namespace': robot_namespace,
                'cmd_vel_topic': cmd_vel_topic,
                'camera_servo_topic': camera_servo_topic,
            }.items(),
            condition=mode_selected(teleop_mode, 'keyboard_servo'),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('robot_bringup'),
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
            condition=mode_selected(teleop_mode, 'ps5'),
        ),
    ])
