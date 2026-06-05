#!/bin/bash
set -euo pipefail

# Rock64 Ubuntu setup for the Rock64 Robot host control stack.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Auto-detect the ros2_ws directory relative to this script.
ROS2_WS=""
for candidate in \
    "$REPO_ROOT/ros2_ws" \
    "$HOME/rock64_ros2_ws" \
    "$HOME/ros2_ws"; do
    if [[ -f "$candidate/requirements.txt" ]]; then
        ROS2_WS="$candidate"
        break
    fi
done

if [[ -z "$ROS2_WS" ]]; then
    echo "ERROR: Could not locate ros2_ws/requirements.txt." >&2
    echo "Pass the workspace path as an argument, e.g.:" >&2
    echo "  $0 /home/\$USER/rock64_ros2_ws" >&2
    exit 1
fi

echo "==> Installing system packages"
sudo apt update
sudo apt install -y python3 python3-pip python3-opencv git

echo "==> Upgrading pip"
python3 -m pip install --upgrade pip

echo "==> Installing Python dependencies from $ROS2_WS/requirements.txt"
python3 -m pip install -r "$ROS2_WS/requirements.txt"

echo "==> Adding $USER to dialout group"
sudo usermod -a -G dialout "$USER"

echo ""
echo "Rock64 host control setup complete."
echo "Log out and log back in to apply dialout group changes."
