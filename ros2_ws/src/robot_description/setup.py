import glob
import os

from setuptools import setup

package_name = 'robot_description'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (
            os.path.join('share', package_name, 'urdf'),
            glob.glob('urdf/*'),
        ),
        (
            os.path.join('share', package_name, 'meshes'),
            glob.glob('meshes/*'),
        ),
        (
            os.path.join('share', package_name, 'launch'),
            glob.glob('launch/*'),
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Robot Developer',
    maintainer_email='developer@example.com',
    description='Robot description scaffold for future Rock64 URDF and Gazebo assets.',
    license='Apache License 2.0',
)