from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


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
        Node(
            package='robot_control',
            executable='keyboard_teleop',
            namespace=robot_namespace,
            name='keyboard_teleop',
            output='screen',
            arguments=[
                '--cmd-vel-topic', cmd_vel_topic,
                '--camera-servo-topic', camera_servo_topic,
                '--linear-speed', linear_speed,
                '--angular-speed', angular_speed,
                '--publish-rate', publish_rate,
                '--servo-step', servo_step,
                '--servo-repeat-hz', servo_repeat_hz,
            ],
        ),
    ])
