import os
import glob
from setuptools import setup

package_name = 'robot_bringup'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (
            os.path.join('share', package_name, 'launch'),
            glob.glob('launch/*.launch.py')
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rock64wsl',
    maintainer_email='rock64wsl@todo.todo',
    description='ROS 2 package for Rock64 Robot',
    license='Apache License 2.0',
    entry_points={
        'console_scripts': [
            # 2. UPDATED these paths to point to 'robot_bringup'
            # Only include the ones that actually exist in your src/robot_bringup folder!
            'ps5_ros_bridge = robot_bringup.ps5_ros_bridge:main',
        ],
    },
)