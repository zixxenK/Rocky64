#!/usr/bin/env bash
# =============================================================================
#  rock64_systemd_start.sh  —  Systemd startup wrapper for Rock64 robot
#
#  This script is launched by systemd on boot and handles:
#    - Network connectivity waiting with timeout
#    - Hardware detection (Arduino, camera) with timeout and fallback
#    - ROS2 environment setup with graceful build handling
#    - Hardware bridge node startup
#    - Optional local teleop if controller detected
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_FILE="/etc/rock64-robot/systemd_config.conf"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values (overridden by config file)
NETWORK_WAIT_TIMEOUT=60
HARDWARE_DETECTION_TIMEOUT=30
CAMERA_DETECTION_TIMEOUT=30
SERIAL_RECONNECT_DELAY=5
ALLOW_START_WITHOUT_ARDUINO=false
ALLOW_START_WITHOUT_CAMERA=false
WORKSPACE_PATH=""
ROS_DISTRO="foxy"
SKIP_BUILD=true
ROBOT_NAMESPACE="rock64_1"
SERIAL_PORT="auto"
BAUD_RATE=115200
CAMERA_IP_STATION="192.168.1.153"
CAMERA_IP_AP="192.168.4.1"
CAMERA_PORT=80
NETWORK_MODE="auto"
EXPECTED_SSID="TELUS4424"
DISCOVERY_SERVER="192.168.1.159:11811"
ROS_DOMAIN_ID=0
LOG_LEVEL="INFO"
LOG_TO_SYSLOG=true
LOG_FILE="/var/log/rock64-robot.log"
SERVICE_USER="rocky64"
SERVICE_GROUP="dialout"

# ---------------------------------------------------------------------------
# Logging functions
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'

log() {
  local level="$1"
  shift
  local message="$*"
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  
  # Output to stdout/stderr based on level
  if [[ "$level" == "ERROR" ]]; then
    echo -e "${RED}[${timestamp}] [${level}]${NC} ${message}" >&2
  elif [[ "$level" == "WARN" ]]; then
    echo -e "${YELLOW}[${timestamp}] [${level}]${NC} ${message}" >&2
  else
    echo -e "${GREEN}[${timestamp}] [${level}]${NC} ${message}"
  fi
  
  # Log to file if configured
  if [[ "$LOG_TO_SYSLOG" == "true" ]]; then
    logger -t "rock64-robot" "[$level] $message"
  fi
  
  if [[ -n "$LOG_FILE" ]]; then
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE" 2>/dev/null || true
  fi
}

log_info()  { log "INFO"  "$*"; }
log_warn()  { log "WARN"  "$*"; }
log_error() { log "ERROR" "$*"; }
log_debug() { [[ "$LOG_LEVEL" == "DEBUG" ]] && log "DEBUG" "$*"; }

# ---------------------------------------------------------------------------
# Load configuration
# ---------------------------------------------------------------------------
load_config() {
  log_info "Loading configuration from $CONFIG_FILE"
  
  if [[ -f "$CONFIG_FILE" ]]; then
    # Source the config file, but be careful with spaces in paths
    while IFS='=' read -r key value; do
      # Skip comments and empty lines
      [[ "$key" =~ ^#.*$ ]] && continue
      [[ -z "$key" ]] && continue
      
      # Remove leading/trailing whitespace
      key=$(echo "$key" | xargs)
      value=$(echo "$value" | xargs)
      
      # Export as variable
      export "$key=$value"
    done < "$CONFIG_FILE"
    
    log_info "Configuration loaded successfully"
  else
    log_warn "Configuration file not found: $CONFIG_FILE, using defaults"
  fi
}

# ---------------------------------------------------------------------------
# Network functions
# ---------------------------------------------------------------------------
wait_for_network() {
  local timeout="${1:-$NETWORK_WAIT_TIMEOUT}"
  log_info "Waiting for network connectivity (timeout: ${timeout}s)"
  
  local elapsed=0
  while [[ $elapsed -lt $timeout ]]; do
    # Check if we can reach the gateway or a known IP
    if ping -c 1 -W 2 8.8.8.8 &>/dev/null || \
       ping -c 1 -W 2 "${DISCOVERY_SERVER%:*}" &>/dev/null; then
      log_info "Network is ready"
      return 0
    fi
    
    sleep 2
    elapsed=$((elapsed + 2))
    log_debug "Still waiting for network... (${elapsed}/${timeout}s)"
  done
  
  log_error "Network did not become ready within ${timeout}s"
  return 1
}

detect_network_mode() {
  local mode="$NETWORK_MODE"
  
  if [[ "$mode" != "auto" ]]; then
    echo "$mode"
    return 0
  fi
  
  # Auto-detect based on WiFi availability
  if command -v nmcli >/dev/null 2>&1; then
    if nmcli -t -f ssid dev wifi | grep -q "^${EXPECTED_SSID}$"; then
      echo "station"
      log_info "Detected network mode: station (SSID ${EXPECTED_SSID} available)"
    else
      echo "ap"
      log_info "Detected network mode: ap (SSID ${EXPECTED_SSID} not available)"
    fi
  elif command -v iwlist >/dev/null 2>&1; then
    if iwlist scan 2>/dev/null | grep -q "${EXPECTED_SSID}"; then
      echo "station"
      log_info "Detected network mode: station (SSID ${EXPECTED_SSID} available)"
    else
      echo "ap"
      log_info "Detected network mode: ap (SSID ${EXPECTED_SSID} not available)"
    fi
  else
    # Default to station mode if we can't detect
    echo "station"
    log_warn "Cannot detect network mode, defaulting to station"
  fi
}

# ---------------------------------------------------------------------------
# Hardware detection functions
# ---------------------------------------------------------------------------
detect_serial_port() {
  local port="$SERIAL_PORT"
  
  if [[ "$port" != "auto" ]]; then
    echo "$port"
    return 0
  fi
  
  # Auto-detect serial port
  log_info "Auto-detecting serial port"
  
  if [[ -e "/dev/ttyUSB0" ]]; then
    echo "/dev/ttyUSB0"
    log_info "Detected serial port: /dev/ttyUSB0"
    return 0
  elif [[ -e "/dev/ttyACM0" ]]; then
    echo "/dev/ttyACM0"
    log_info "Detected serial port: /dev/ttyACM0"
    return 0
  else
    # Try to find any Arduino/USB serial device
    for device in /dev/ttyUSB* /dev/ttyACM*; do
      if [[ -e "$device" ]]; then
        echo "$device"
        log_info "Detected serial port: $device"
        return 0
      fi
    done
    
    log_warn "No serial port detected"
    return 1
  fi
}

wait_for_arduino() {
  local timeout="${1:-$HARDWARE_DETECTION_TIMEOUT}"
  log_info "Waiting for Arduino serial connection (timeout: ${timeout}s)"
  
  local elapsed=0
  while [[ $elapsed -lt $timeout ]]; do
    local port
    port=$(detect_serial_port)
    
    if [[ -n "$port" && -e "$port" ]]; then
      # Try to open the port to verify it's accessible
      if python3 -c "
import serial
try:
    ser = serial.Serial('$port', 115200, timeout=1)
    ser.close()
    exit(0)
except:
    exit(1)
" 2>/dev/null; then
        log_info "Arduino detected and accessible at $port"
        echo "$port"
        return 0
      fi
    fi
    
    sleep 2
    elapsed=$((elapsed + 2))
    log_debug "Still waiting for Arduino... (${elapsed}/${timeout}s)"
  done
  
  log_error "Arduino not detected within ${timeout}s"
  return 1
}

wait_for_camera() {
  local timeout="${1:-$CAMERA_DETECTION_TIMEOUT}"
  local network_mode
  network_mode=$(detect_network_mode)
  
  local camera_ip
  if [[ "$network_mode" == "station" ]]; then
    camera_ip="$CAMERA_IP_STATION"
  else
    camera_ip="$CAMERA_IP_AP"
  fi
  
  local camera_url="http://${camera_ip}:${CAMERA_PORT}/stream"
  
  log_info "Waiting for camera at $camera_url (timeout: ${timeout}s)"
  
  local elapsed=0
  while [[ $elapsed -lt $timeout ]]; do
    # Try to fetch a single frame from the camera
    if curl -s --max-time 3 "$camera_url" >/dev/null 2>&1; then
      log_info "Camera detected at $camera_url"
      echo "$camera_url"
      return 0
    fi
    
    sleep 2
    elapsed=$((elapsed + 2))
    log_debug "Still waiting for camera... (${elapsed}/${timeout}s)"
  done
  
  log_error "Camera not detected within ${timeout}s"
  return 1
}

detect_controller() {
  log_info "Checking for local controller connection"
  
  # Check for PS5 controller via evdev
  if command -v evdev-list >/dev/null 2>&1; then
    if evdev-list 2>/dev/null | grep -i "DualSense\|Sony\|PS5" >/dev/null; then
      log_info "PS5 DualSense controller detected"
      echo "ps5"
      return 0
    fi
  elif [[ -d "/dev/input" ]]; then
    # Fallback: check input devices
    for device in /dev/input/event*; do
      if [[ -e "$device" ]]; then
        if udevadm info --name="$device" 2>/dev/null | grep -i "DualSense\|Sony\|PS5" >/dev/null; then
          log_info "PS5 DualSense controller detected at $device"
          echo "ps5"
          return 0
        fi
      fi
    done
  fi
  
  log_debug "No PS5 controller detected"
  return 1
}

# ---------------------------------------------------------------------------
# ROS2 environment setup
# ---------------------------------------------------------------------------
setup_ros2_environment() {
  log_info "Setting up ROS2 environment"
  
  # Source ROS2 installation
  if [[ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]]; then
    # shellcheck source=/dev/null
    source "/opt/ros/${ROS_DISTRO}/setup.bash"
    log_info "Sourced ROS2 ${ROS_DISTRO} environment"
  else
    log_error "ROS2 ${ROS_DISTRO} not found at /opt/ros/${ROS_DISTRO}/setup.bash"
    return 1
  fi
  
  # Source workspace
  local workspace="$WORKSPACE_PATH"
  if [[ -z "$workspace" ]]; then
    # Auto-detect workspace
    workspace="$SCRIPT_DIR"
  fi
  
  # Expand workspace path (handle spaces)
  workspace=$(eval echo "$workspace")
  
  if [[ -f "${workspace}/install/setup.bash" ]]; then
    # shellcheck source=/dev/null
    source "${workspace}/install/setup.bash"
    log_info "Sourced workspace at $workspace"
  else
    log_warn "Workspace install/setup.bash not found at ${workspace}/install/setup.bash"
    
    # Try to build if configured
    if [[ "$SKIP_BUILD" != "true" ]]; then
      log_info "Attempting to build workspace..."
      cd "$workspace"
      if colcon build --symlink-install 2>&1 | tee -a "$LOG_FILE"; then
        # shellcheck source=/dev/null
        source "${workspace}/install/setup.bash"
        log_info "Workspace built and sourced successfully"
      else
        log_error "Workspace build failed"
        return 1
      fi
    else
      log_error "Workspace not built and SKIP_BUILD=true, cannot continue"
      return 1
    fi
  fi
  
  # Set ROS2 environment variables
  export ROS_DOMAIN_ID="$ROS_DOMAIN_ID"
  export ROS_LOCALHOST_ONLY=0
  
  if [[ -n "$DISCOVERY_SERVER" ]]; then
    export ROS_DISCOVERY_SERVER="$DISCOVERY_SERVER"
    log_info "Set ROS_DISCOVERY_SERVER=$DISCOVERY_SERVER"
  fi
  
  return 0
}

# ---------------------------------------------------------------------------
# User permissions setup
# ---------------------------------------------------------------------------
setup_permissions() {
  log_info "Setting up user permissions"
  
  # Ensure user is in dialout group for serial port access
  if id "$SERVICE_USER" &>/dev/null; then
    if groups "$SERVICE_USER" | grep -q "\bdialout\b"; then
      log_info "User $SERVICE_USER is already in dialout group"
    else
      log_warn "User $SERVICE_USER is not in dialout group, serial access may fail"
      log_warn "Run: sudo usermod -a -G dialout $SERVICE_USER"
    fi
  else
    log_warn "User $SERVICE_USER does not exist, running as current user"
    SERVICE_USER="$(whoami)"
  fi
}

# ---------------------------------------------------------------------------
# Main startup sequence
# ---------------------------------------------------------------------------
main() {
  log_info "=== Rock64 Robot Systemd Startup ==="
  log_info "Starting as user: $(whoami)"
  
  # Load configuration
  load_config
  
  # Setup permissions
  setup_permissions
  
  # Wait for network
  if ! wait_for_network; then
    log_error "Failed to wait for network, aborting startup"
    exit 1
  fi
  
  # Detect network mode
  local network_mode
  network_mode=$(detect_network_mode)
  
  # Wait for hardware
  local arduino_port=""
  local camera_url=""
  local arduino_detected=false
  local camera_detected=false
  
  if wait_for_arduino; then
    arduino_port=$(detect_serial_port)
    arduino_detected=true
  elif [[ "$ALLOW_START_WITHOUT_ARDUINO" == "true" ]]; then
    log_warn "Arduino not detected but ALLOW_START_WITHOUT_ARDUINO=true, continuing without it"
    arduino_port="/dev/ttyUSB0"  # Fallback
  else
    log_error "Arduino not detected and ALLOW_START_WITHOUT_ARDUINO=false, aborting startup"
    exit 1
  fi
  
  if wait_for_camera; then
    camera_url=$(wait_for_camera)
    camera_detected=true
  elif [[ "$ALLOW_START_WITHOUT_CAMERA" == "true" ]]; then
    log_warn "Camera not detected but ALLOW_START_WITHOUT_CAMERA=true, continuing without it"
    # Use fallback URL based on network mode
    if [[ "$network_mode" == "station" ]]; then
      camera_url="http://${CAMERA_IP_STATION}:${CAMERA_PORT}/stream"
    else
      camera_url="http://${CAMERA_IP_AP}:${CAMERA_PORT}/stream"
    fi
  else
    log_error "Camera not detected and ALLOW_START_WITHOUT_CAMERA=false, aborting startup"
    exit 1
  fi
  
  # Setup ROS2 environment
  if ! setup_ros2_environment; then
    log_error "Failed to setup ROS2 environment, aborting startup"
    exit 1
  fi
  
  # Check for local controller
  local controller_type
  controller_type=$(detect_controller) || controller_type=""
  
  # Launch ROS2 hardware bridge
  log_info "Launching ROS2 hardware bridge nodes"
  log_info "Configuration: namespace=$ROBOT_NAMESPACE, serial=$arduino_port, camera=$camera_url"
  
  # Build launch command
  local launch_args=(
    "--role" "rock64"
    "--workspace" "$WORKSPACE_PATH"
    "--serial-port" "$arduino_port"
    "--baud-rate" "$BAUD_RATE"
    "--camera-ip" "${camera_url#http://}"  # Remove http:// prefix
    "--camera-port" "$CAMERA_PORT"
    "--namespace" "$ROBOT_NAMESPACE"
    "--network-mode" "$network_mode"
    "--discovery-server" "$DISCOVERY_SERVER"
    "--domain-id" "$ROS_DOMAIN_ID"
    "--skip-build"
  )
  
  # Add teleop mode if controller detected
  if [[ -n "$controller_type" ]]; then
    launch_args+=("--teleop-mode" "$controller_type")
    log_info "Starting with local $controller_type teleop"
  else
    launch_args+=("--teleop-mode" "none")
    log_info "Starting without local teleop (waiting for PC connection)"
  fi
  
  # Launch the robot
  log_info "Executing: ${SCRIPT_DIR}/../robot_start.sh ${launch_args[*]}"
  
  cd "$SCRIPT_DIR/.."
  exec ./robot_start.sh "${launch_args[@]}"
}

# Run main function
main "$@"
