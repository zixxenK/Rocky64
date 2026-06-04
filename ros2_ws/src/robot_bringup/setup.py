import glob
import os

from setuptools import setup

package_name = 'robot_bringup'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        # This line is the "Phonebook" entry
        ('share/ament_index/resource_index/packages', ['resource/robot_bringup']),
        # This line includes your package.xml
        ('share/robot_bringup', ['package.xml']),
        # This line includes your launch files
        (os.path.join('share', 'robot_bringup', 'launch'), glob.glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Robot Developer',
    maintainer_email='developer@example.com',
    description='ROS 2 bringup package for Rock64 robot runtime entrypoints.',
    license='Apache License 2.0',
)