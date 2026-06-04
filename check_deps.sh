#!/bin/bash
source /opt/ros/foxy/setup.bash 2>/dev/null
echo "=== Python version ==="
python3 --version

echo "=== ROS2 packages ==="
python3 -c "import rclpy; print('rclpy: OK')" 2>&1
python3 -c "from geometry_msgs.msg import Twist; print('geometry_msgs: OK')" 2>&1
python3 -c "from std_msgs.msg import Int16, String; print('std_msgs: OK')" 2>&1

echo "=== pip packages ==="
python3 -m pip show pyserial pygame evdev 2>&1 | grep -E "Name:|Version:"

echo "=== opencv ==="
python3 -c "import cv2; print('cv2 version:', cv2.__version__)" 2>&1

echo "=== colcon workspace ==="
if [ -f "/mnt/c/Desktop/Rock64 Robot/ros2_ws/install/setup.bash" ]; then
    source "/mnt/c/Desktop/Rock64 Robot/ros2_ws/install/setup.bash" 2>/dev/null
    python3 -c "import robot_control; print('robot_control pkg: OK')" 2>&1
    echo "workspace install found at /mnt/c/Desktop/Rock64 Robot/ros2_ws/install"
else
    echo "workspace install NOT found - need to run colcon build in WSL"
fi

echo "=== Done ==="
