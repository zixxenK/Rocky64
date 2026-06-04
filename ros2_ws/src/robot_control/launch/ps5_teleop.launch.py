from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


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
        Node(
            package='robot_control',
            executable='ps5_ros_bridge',
            namespace=robot_namespace,
            name='ps5_ros_bridge',
            output='screen',
            arguments=[
                '--cmd-vel-topic', cmd_vel_topic,
                '--camera-servo-topic', camera_servo_topic,
                '--joystick-index', joystick_index,
                '--controller-name', controller_name,
                '--poll-interval', poll_interval,
                '--leftx-axis', leftx_axis,
                '--lefty-axis', lefty_axis,
                '--rightx-axis', rightx_axis,
                '--l2-axis', l2_axis,
                '--r2-axis', r2_axis,
            ],
        ),
    ])
