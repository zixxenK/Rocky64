#!/bin/bash
# Quick dependency check — works on the Rock64 and WSL/Linux dev hosts.
set -u

source /opt/ros/foxy/setup.bash 2>/dev/null || true

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
# Auto-detect workspace — try common locations.
WS=""
for candidate in \
    "$HOME/rock64_ros2_ws" \
    "$HOME/ros2_ws" \
    "$HOME/Rock64 Robot/ros2_ws" \
    "/mnt/c/Desktop/Rock64 Robot/ros2_ws"; do
    if [[ -f "$candidate/install/setup.bash" ]]; then
        WS="$candidate"
        break
    fi
done

if [[ -n "$WS" ]]; then
    # shellcheck disable=SC1091
    source "$WS/install/setup.bash" 2>/dev/null || true
    python3 -c "import robot_control; print('robot_control pkg: OK')" 2>&1
    echo "workspace install found at $WS/install"
else
    echo "workspace install NOT found — need to run colcon build"
    echo "  checked: ~/rock64_ros2_ws, ~/ros2_ws, ~/Rock64 Robot/ros2_ws, /mnt/c/Desktop/Rock64 Robot/ros2_ws"
fi

echo "=== Done ==="
