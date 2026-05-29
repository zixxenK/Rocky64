cmake_minimum_required(VERSION 3.0.2)
project(ps5_controller_bridge)

find_package(catkin REQUIRED COMPONENTS
  rospy
  geometry_msgs
)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/ps5_ros_bridge.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
