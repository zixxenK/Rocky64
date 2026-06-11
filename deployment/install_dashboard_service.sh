#!/bin/bash
# install_dashboard_service.sh - Install unified dashboard as systemd service on Rock64
#
# This script installs the unified dashboard as a systemd service that auto-starts
# on Rock64 boot. Run this script ON THE ROCK64.
#
# Usage:
#   sudo ./install_dashboard_service.sh
#   sudo ./install_dashboard_service.sh --uninstall

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_CONTROL_DIR="$(dirname "$SCRIPT_DIR")/host_control"
SERVICE_FILE="$SCRIPT_DIR/rock64-dashboard.service"
SERVICE_NAME="rock64-dashboard"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check if on Rock64/Linux
check_platform() {
    if [[ ! -f /etc/os-release ]]; then
        print_error "Cannot detect OS. This script is for Linux/Rock64 only."
        exit 1
    fi
    
    . /etc/os-release
    print_info "Detected platform: $PRETTY_NAME"
}

# Check dependencies
check_dependencies() {
    print_info "Checking dependencies..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "python3 not found. Install with: sudo apt install python3"
        exit 1
    fi
    
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3 not found. Install with: sudo apt install python3-pip"
        exit 1
    fi
    
    print_info "Dependencies OK"
}

# Install Python dependencies
install_python_deps() {
    print_info "Installing Python dependencies..."
    
    if [[ -f "$HOST_CONTROL_DIR/../../requirements.txt" ]]; then
        pip3 install -r "$HOST_CONTROL_DIR/../../requirements.txt" || {
            print_warn "Failed to install from requirements.txt, continuing anyway..."
        }
    fi
    
    # Install Flask and SocketIO if not already installed
    pip3 install flask flask-socketio || true
    
    print_info "Python dependencies installed"
}

# Setup permissions
setup_permissions() {
    print_info "Setting up permissions..."
    
    # Add rock64 user to dialout group for serial access
    usermod -a -G dialout rock64 || true
    
    # Make scripts executable
    chmod +x "$HOST_CONTROL_DIR/unified_dashboard.py"
    chmod +x "$HOST_CONTROL_DIR/dashboard_boot.py"
    chmod +x "$HOST_CONTROL_DIR/agent_controller.py"
    
    print_info "Permissions set"
}

# Install systemd service
install_service() {
    print_info "Installing systemd service..."
    
    # Copy service file
    cp "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME.service"
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable service (start on boot)
    systemctl enable "$SERVICE_NAME"
    
    print_info "Service installed and enabled"
}

# Start service
start_service() {
    print_info "Starting $SERVICE_NAME service..."
    
    systemctl start "$SERVICE_NAME"
    
    # Wait a moment for service to start
    sleep 3
    
    # Check status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_info "Service started successfully"
        systemctl status "$SERVICE_NAME" --no-pager
    else
        print_error "Service failed to start"
        systemctl status "$SERVICE_NAME" --no-pager
        journalctl -u "$SERVICE_NAME" -n 50 --no-pager
        exit 1
    fi
}

# Uninstall service
uninstall_service() {
    print_info "Uninstalling $SERVICE_NAME service..."
    
    # Stop service
    systemctl stop "$SERVICE_NAME" || true
    
    # Disable service
    systemctl disable "$SERVICE_NAME" || true
    
    # Remove service file
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    
    # Reload systemd
    systemctl daemon-reload
    
    print_info "Service uninstalled"
}

# Show service status
show_status() {
    print_info "Service status:"
    systemctl status "$SERVICE_NAME" --no-pager || true
    
    echo ""
    print_info "Recent logs:"
    journalctl -u "$SERVICE_NAME" -n 50 --no-pager || true
}

# Main installation
main_install() {
    print_info "=== Installing Unified Dashboard Service ==="
    echo ""
    
    check_root
    check_platform
    check_dependencies
    install_python_deps
    setup_permissions
    install_service
    start_service
    
    echo ""
    print_info "=== Installation Complete ==="
    print_info "Dashboard will be available at: http://$(hostname -I | awk '{print $1}'):5000"
    print_info "Service management commands:"
    print_info "  Start:   sudo systemctl start $SERVICE_NAME"
    print_info "  Stop:    sudo systemctl stop $SERVICE_NAME"
    print_info "  Restart: sudo systemctl restart $SERVICE_NAME"
    print_info "  Status:  sudo systemctl status $SERVICE_NAME"
    print_info "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
}

# Main
case "${1:-}" in
    --uninstall)
        check_root
        uninstall_service
        ;;
    --status)
        check_root
        show_status
        ;;
    --help)
        echo "Usage: $0 [OPTION]"
        echo "Options:"
        echo "  (no args)  Install and start the service"
        echo "  --uninstall Uninstall the service"
        echo "  --status   Show service status and logs"
        echo "  --help     Show this help message"
        ;;
    *)
        main_install
        ;;
esac
