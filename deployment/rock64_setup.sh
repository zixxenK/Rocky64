#!/bin/bash
set -e

# Rock64 Ubuntu setup for the Rock64 Robot host control stack.
# This script installs dependencies and optionally sets up systemd services.

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="/etc/rock64-robot/systemd_config.conf"
INSTALL_SYSTEMD=true
INSTALL_ROCK64_SERVICE=true
INSTALL_PC_SERVICE=false

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-systemd)
      INSTALL_SYSTEMD=false
      shift
      ;;
    --rock64-only)
      INSTALL_ROCK64_SERVICE=true
      INSTALL_PC_SERVICE=false
      shift
      ;;
    --pc-only)
      INSTALL_ROCK64_SERVICE=false
      INSTALL_PC_SERVICE=true
      shift
      ;;
    --both)
      INSTALL_ROCK64_SERVICE=true
      INSTALL_PC_SERVICE=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo "Options:"
      echo "  --no-systemd       Skip systemd service installation"
      echo "  --rock64-only      Install only Rock64 robot service"
      echo "  --pc-only          Install only PC operator service"
      echo "  --both             Install both Rock64 and PC services"
      echo "  --help, -h         Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# -----------------------------------------------------------------------------
# Install system dependencies
# -----------------------------------------------------------------------------
echo "=== Installing system dependencies ==="
sudo apt update
sudo apt install -y python3 python3-pip python3-opencv git curl net-tools

# Install evdev for PS5 controller detection
echo "Installing evdev for PS5 controller support"
python3 -m pip install evdev --user 2>/dev/null || sudo python3 -m pip install evdev

# -----------------------------------------------------------------------------
# Install Python dependencies
# -----------------------------------------------------------------------------
echo "=== Installing Python dependencies ==="
python3 -m pip install --upgrade pip
python3 -m pip install -r "$PROJECT_ROOT/ros2_ws/requirements.txt"

# -----------------------------------------------------------------------------
# Setup user permissions
# -----------------------------------------------------------------------------
echo "=== Setting up user permissions ==="
sudo usermod -a -G dialout $USER
sudo usermod -a -G input $USER  # For controller access

# -----------------------------------------------------------------------------
# Install systemd services
# -----------------------------------------------------------------------------
if [[ "$INSTALL_SYSTEMD" == "true" ]]; then
  echo "=== Installing systemd services ==="
  
  # Create config directory
  sudo mkdir -p /etc/rock64-robot
  
  # Install configuration file
  echo "Installing systemd configuration to $CONFIG_FILE"
  sudo cp "$SCRIPT_DIR/systemd_config.conf" "$CONFIG_FILE"
  
  # Allow user to edit config
  sudo chown $USER:$USER /etc/rock64-robot/systemd_config.conf
  sudo chmod 644 /etc/rock64-robot/systemd_config.conf
  
  # Make startup scripts executable
  chmod +x "$SCRIPT_DIR/rock64_systemd_start.sh"
  chmod +x "$SCRIPT_DIR/pc_systemd_start.sh"
  
  # Install Rock64 robot service
  if [[ "$INSTALL_ROCK64_SERVICE" == "true" ]]; then
    echo "Installing Rock64 robot service"
    sudo cp "$SCRIPT_DIR/rock64-robot.service" /etc/systemd/system/
    
    # Replace user placeholder in service file
    sudo sed -i "s/User=rocky64/User=$USER/" /etc/systemd/system/rock64-robot.service
    sudo sed -i "s|WorkingDirectory=/home/rocky64/Rock64 Robot/ros2_ws|WorkingDirectory=$PROJECT_ROOT/ros2_ws|" /etc/systemd/system/rock64-robot.service
    sudo sed -i "s|ExecStart=/home/rocky64/Rock64\\ Robot/deployment/rock64_systemd_start.sh|ExecStart=$SCRIPT_DIR/rock64_systemd_start.sh|" /etc/systemd/system/rock64-robot.service
    sudo sed -i "s|ReadWritePaths=/home/rocky64/Rock64\\ Robot|ReadWritePaths=$PROJECT_ROOT|" /etc/systemd/system/rock64-robot.service
    
    sudo systemctl daemon-reload
    sudo systemctl enable rock64-robot.service
    echo "Rock64 robot service installed and enabled"
  fi
  
  # Install PC operator service
  if [[ "$INSTALL_PC_SERVICE" == "true" ]]; then
    echo "Installing PC operator service"
    sudo cp "$SCRIPT_DIR/rock64-operator.service" /etc/systemd/system/
    
    # Replace user placeholder in service file
    sudo sed -i "s/User=%i/User=$USER/" /etc/systemd/system/rock64-operator.service
    sudo sed -i "s|%h/Rock64 Robot/ros2_ws|$PROJECT_ROOT/ros2_ws|" /etc/systemd/system/rock64-operator.service
    sudo sed -i "s|ExecStart=%h/Rock64\\ Robot/deployment/pc_systemd_start.sh|ExecStart=$SCRIPT_DIR/pc_systemd_start.sh|" /etc/systemd/system/rock64-operator.service
    sudo sed -i "s|ReadWritePaths=%h/Rock64\\ Robot|ReadWritePaths=$PROJECT_ROOT|" /etc/systemd/system/rock64-operator.service
    
    sudo systemctl daemon-reload
    sudo systemctl enable rock64-operator.service
    echo "PC operator service installed and enabled"
  fi
  
  echo "=== Systemd services installation complete ==="
  echo "To start services immediately:"
  [[ "$INSTALL_ROCK64_SERVICE" == "true" ]] && echo "  sudo systemctl start rock64-robot.service"
  [[ "$INSTALL_PC_SERVICE" == "true" ]] && echo "  sudo systemctl start rock64-operator.service"
  echo ""
  echo "To view service logs:"
  echo "  sudo journalctl -u rock64-robot.service -f"
  echo "  sudo journalctl -u rock64-operator.service -f"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Rock64 host control setup complete ==="
echo ""
echo "IMPORTANT: Log out and log back in to apply dialout group changes."
echo ""
echo "Configuration file: $CONFIG_FILE"
echo "Edit this file to customize service behavior (IPs, timeouts, etc.)"
echo ""
echo "Service management commands:"
[[ "$INSTALL_ROCK64_SERVICE" == "true" ]] && echo "  Rock64 service: sudo systemctl {start|stop|restart|status} rock64-robot.service"
[[ "$INSTALL_PC_SERVICE" == "true" ]] && echo "  PC service:     sudo systemctl {start|stop|restart|status} rock64-operator.service"
echo ""
echo "View logs:"
echo "  sudo journalctl -u rock64-robot.service -f"
echo "  sudo journalctl -u rock64-operator.service -f"
