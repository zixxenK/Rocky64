from setuptools import setup

package_name = 'robot_control'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'pyserial>=3.5', 'opencv-python>=4.7.0'],
    zip_safe=True,
    maintainer='Robot Developer',
    maintainer_email='developer@example.com',
    description='ROS 2 package for Rock64 robot serial control',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'robot_control_node = robot_control.robot_control_node:main',
        ],
    },
)
