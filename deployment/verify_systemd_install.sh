#!/bin/bash
# =============================================================================
#  verify_systemd_install.sh  —  Verify systemd service installation
#
#  This script checks if the systemd services are properly installed and configured.
#  Run this after installing the services to verify the installation.
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
info() { echo -e "[INFO] $*"; }

error_count=0
warn_count=0

# Check function
check() {
  if eval "$1"; then
    pass "$2"
    return 0
  else
    fail "$2"
    ((error_count++))
    return 1
  fi
}

echo "=== Rock64 Robot Systemd Service Verification ==="
echo ""

# Check configuration file
echo "=== Checking Configuration ==="
check "[ -f /etc/rock64-robot/systemd_config.conf ]" \
  "Configuration file exists at /etc/rock64-robot/systemd_config.conf"

check "[ -r /etc/rock64-robot/systemd_config.conf ]" \
  "Configuration file is readable"

check "[ -w /etc/rock64-robot/systemd_config.conf ]" \
  "Configuration file is writable by current user"

echo ""

# Check Rock64 service files
echo "=== Checking Rock64 Robot Service ==="
check "[ -f /etc/systemd/system/rock64-robot.service ]" \
  "Rock64 robot service file exists"

check "[ -f /home/\$(whoami)/Rock64\ Robot/deployment/rock64_systemd_start.sh ]" \
  "Rock64 startup wrapper script exists"

check "[ -x /home/\$(whoami)/Rock64\ Robot/deployment/rock64_systemd_start.sh ]" \
  "Rock64 startup wrapper script is executable"

# Check service content
if [ -f /etc/systemd/system/rock64-robot.service ]; then
  check "grep -q 'rock64_systemd_start.sh' /etc/systemd/system/rock64-robot.service" \
    "Rock64 service file references correct startup script"
  
  check "grep -q 'After=network-online.target' /etc/systemd/system/rock64-robot.service" \
    "Rock64 service waits for network"
  
  check "grep -q 'Wants=network-online.target' /etc/systemd/system/rock64-robot.service" \
    "Rock64 service wants network-online.target"
fi

echo ""

# Check PC service files
echo "=== Checking PC Operator Service ==="
check "[ -f /etc/systemd/system/rock64-operator.service ]" \
  "PC operator service file exists"

check "[ -f /home/\$(whoami)/Rock64\ Robot/deployment/pc_systemd_start.sh ]" \
  "PC startup wrapper script exists"

check "[ -x /home/\$(whoami)/Rock64\ Robot/deployment/pc_systemd_start.sh ]" \
  "PC startup wrapper script is executable"

# Check service content
if [ -f /etc/systemd/system/rock64-operator.service ]; then
  check "grep -q 'pc_systemd_start.sh' /etc/systemd/system/rock64-operator.service" \
    "PC service file references correct startup script"
  
  check "grep -q 'After=network-online.target' /etc/systemd/system/rock64-operator.service" \
    "PC service waits for network"
  
  check "grep -q 'rock64-robot.service' /etc/systemd/system/rock64-operator.service" \
    "PC service depends on rock64-robot.service"
fi

echo ""

# Check systemd configuration
echo "=== Checking Systemd Configuration ==="
check "systemctl is-enabled rock64-robot.service 2>/dev/null || true" \
  "Rock64 robot service is enabled" || \
  warn "Rock64 robot service is not enabled (run: sudo systemctl enable rock64-robot.service)"

check "systemctl is-enabled rock64-operator.service 2>/dev/null || true" \
  "PC operator service is enabled" || \
  warn "PC operator service is not enabled (run: sudo systemctl enable rock64-operator.service)"

echo ""

# Check user permissions
echo "=== Checking User Permissions ==="
current_user=$(whoami)
check "groups \$current_user | grep -q 'dialout'" \
  "User $current_user is in dialout group (for serial access)" || \
  warn "User $current_user is not in dialout group (run: sudo usermod -a -G dialout $current_user)"

check "groups \$current_user | grep -q 'input'" \
  "User $current_user is in input group (for controller access)" || \
  warn "User $current_user is not in input group (run: sudo usermod -a -G input $current_user)"

echo ""

# Check dependencies
echo "=== Checking Dependencies ==="
check "command -v python3 >/dev/null 2>&1" \
  "Python3 is installed"

check "python3 -c 'import serial' 2>/dev/null" \
  "pyserial is installed"

check "python3 -c 'import evdev' 2>/dev/null" \
  "evdev is installed (for PS5 controller detection)" || \
  warn "evdev is not installed (run: pip install evdev)"

check "command -v systemctl >/dev/null 2>&1" \
  "systemctl is available"

echo ""

# Check network configuration
echo "=== Checking Network Configuration ==="
check "ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1" \
  "Internet connectivity available" || \
  warn "No internet connectivity (services may fail to start)"

# Check Rock64 connectivity if configured
if [ -f /etc/rock64-robot/systemd_config.conf ]; then
  robot_host=$(grep "^ROBOT_HOST=" /etc/rock64-robot/systemd_config.conf | cut -d= -f2)
  if [ -n "$robot_host" ]; then
    check "ping -c 1 -W 2 $robot_host >/dev/null 2>&1" \
      "Can reach Rock64 robot at $robot_host" || \
      warn "Cannot reach Rock64 robot at $robot_host"
  fi
fi

echo ""

# Check hardware
echo "=== Checking Hardware ==="
check "ls /dev/ttyUSB* >/dev/null 2>&1 || ls /dev/ttyACM* >/dev/null 2>&1" \
  "Serial devices available" || \
  warn "No serial devices detected (Arduino may not be connected)"

if command -v evdev-list >/dev/null 2>&1; then
  check "evdev-list 2>/dev/null | grep -qi 'DualSense\|Sony\|PS5'" \
    "PS5 controller detected" || \
    warn "PS5 controller not detected (may not be connected)"
elif [ -d "/dev/input" ]; then
  controller_found=false
  for device in /dev/input/event*; do
    if [ -e "$device" ]; then
      if udevadm info --name="$device" 2>/dev/null | grep -qi "DualSense\|Sony\|PS5"; then
        controller_found=true
        break
      fi
    fi
  done
  check "$controller_found" \
    "PS5 controller detected via udevadm" || \
    warn "PS5 controller not detected (may not be connected)"
fi

echo ""

# Check ROS2
echo "=== Checking ROS2 Installation ==="
if [ -f /etc/rock64-robot/systemd_config.conf ]; then
  ros_distro=$(grep "^ROS_DISTRO=" /etc/rock64-robot/systemd_config.conf | cut -d= -f2)
  if [ -n "$ros_distro" ]; then
    check "[ -f /opt/ros/$ros_distro/setup.bash ]" \
      "ROS2 $ros_distro is installed at /opt/ros/$ros_distro"
  fi
fi

workspace_path=$(grep "^WORKSPACE_PATH=" /etc/rock64-robot/systemd_config.conf | cut -d= -f2)
if [ -n "$workspace_path" ]; then
  workspace_path=$(eval echo "$workspace_path")
  check "[ -d $workspace_path ]" \
    "ROS2 workspace exists at $workspace_path"
  
  check "[ -f $workspace_path/install/setup.bash ]" \
    "ROS2 workspace is built (install/setup.bash exists)"
fi

echo ""

# Summary
echo "=== Verification Summary ==="
if [ $error_count -eq 0 ]; then
  echo -e "${GREEN}All critical checks passed!${NC}"
  echo "Systemd services are properly installed and configured."
  echo ""
  echo "To start services:"
  echo "  sudo systemctl start rock64-robot.service"
  echo "  sudo systemctl start rock64-operator.service"
  echo ""
  echo "To enable auto-start on boot:"
  echo "  sudo systemctl enable rock64-robot.service"
  echo "  sudo systemctl enable rock64-operator.service"
  exit 0
else
  echo -e "${RED}$error_count critical check(s) failed${NC}"
  echo ""
  echo "Please fix the issues above before starting the services."
  echo ""
  echo "Common fixes:"
  echo "  - Add user to dialout group: sudo usermod -a -G dialout \$USER"
  echo "  - Add user to input group: sudo usermod -a -G input \$USER"
  echo "  - Install evdev: pip install evdev"
  echo "  - Enable services: sudo systemctl enable rock64-robot.service"
  echo "  - Build workspace: cd ros2_ws && colcon build"
  exit 1
fi
