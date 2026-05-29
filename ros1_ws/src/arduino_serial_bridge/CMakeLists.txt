cmake_minimum_required(VERSION 3.0.2)
project(arduino_serial_bridge)

find_package(catkin REQUIRED COMPONENTS
  rospy
  geometry_msgs
  std_msgs
)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/arduino_serial_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
