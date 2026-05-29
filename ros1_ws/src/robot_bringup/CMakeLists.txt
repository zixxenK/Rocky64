cmake_minimum_required(VERSION 3.0.2)
project(robot_bringup)

find_package(catkin REQUIRED COMPONENTS
  rospy
  arduino_serial_bridge
  esp32_camera_bridge
  ps5_controller_bridge
)

catkin_package()
