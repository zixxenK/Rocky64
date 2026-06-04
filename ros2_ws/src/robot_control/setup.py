import glob
import os

from setuptools import setup

package_name = 'robot_control'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        (
            'share/ament_index/resource_index/packages',
            [f'resource/{package_name}'],
        ),
        (f'share/{package_name}', ['package.xml']),
        (
            os.path.join('share', package_name, 'launch'),
            glob.glob('launch/*.launch.py') + glob.glob('launch/*.py'),
        ),
        (
            os.path.join('share', package_name, 'config'),
            glob.glob('config/*.yaml'),
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Robot Developer',
    maintainer_email='developer@example.com',
    description='ROS 2 package for Rock64 robot serial control.',
    license='Apache License 2.0',
    entry_points={
        'console_scripts': [
            'arduino_serial_bridge = robot_control.arduino_serial_bridge:main',
            'esp32_camera_bridge = robot_control.esp32_camera_bridge:main',
            'keyboard_teleop = robot_control.keyboard_teleop:main',
            'ps5_ros_bridge = robot_control.ps5_ros_bridge:main',
            'robot_control_node = robot_control.robot_control_node:main',
            'udp_robot_bridge = robot_control.udp_robot_bridge:main',
        ],
    },
)
