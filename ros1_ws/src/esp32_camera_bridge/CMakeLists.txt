cmake_minimum_required(VERSION 3.0.2)
project(esp32_camera_bridge)

find_package(catkin REQUIRED COMPONENTS
  rospy
  sensor_msgs
  cv_bridge
  image_transport
)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/camera_bridge.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
