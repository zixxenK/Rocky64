#!/usr/bin/env bash
# =============================================================================
#  pc_systemd_start.sh  —  Systemd startup wrapper for PC operator
#
#  This script is launched by systemd on boot and handles:
#    - Network connectivity waiting with timeout
#    - PS5 controller detection with priority and fallback logic
#    - ROS2 environment setup with graceful build handling
#    - Teleop node startup (PS5 priority, keyboard fallback)
#    - Connection to Rock64 robot for remote control
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_FILE="/etc/rock64-robot/systemd_config.conf"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values (overridden by config file)
NETWORK_WAIT_TIMEOUT=60
CONTROLLER_DETECTION_TIMEOUT=30
WORKSPACE_PATH=""
ROS_DISTRO="foxy"
SKIP_BUILD=true
ROBOT_NAMESPACE="rock64_1"
ROBOT_HOST="192.168.1.159"
DISCOVERY_SERVER="192.168.1.159:11811"
ROS_DOMAIN_ID=0
PC_TELEOP_MODE="ps5"
JOYSTICK_INDEX=0
CONTROLLER_NAME="DualSense"
FALLBACK_TO_KEYBOARD=true
LOG_LEVEL="INFO"
LOG_TO_SYSLOG=true
LOG_FILE="/var/log/rock64-operator.log"
SERVICE_USER=""

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
    logger -t "rock64-operator" "[$level] $message"
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
    # Check if we can reach the Rock64 robot
    if ping -c 1 -W 2 "$ROBOT_HOST" &>/dev/null; then
      log_info "Network is ready, can reach Rock64 at $ROBOT_HOST"
      return 0
    fi
    
    # Also check general internet connectivity
    if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
      log_info "Network is ready (internet accessible)"
      return 0
    fi
    
    sleep 2
    elapsed=$((elapsed + 2))
    log_debug "Still waiting for network... (${elapsed}/${timeout}s)"
  done
  
  log_error "Network did not become ready within ${timeout}s"
  return 1
}

wait_for_robot() {
  local timeout="${1:-30}"
  log_info "Waiting for Rock64 robot at $ROBOT_HOST (timeout: ${timeout}s)"
  
  local elapsed=0
  while [[ $elapsed -lt $timeout ]]; do
    if ping -c 1 -W 2 "$ROBOT_HOST" &>/dev/null; then
      # Check if ROS2 discovery server is reachable
      if nc -z "${DISCOVERY_SERVER%:*}" "${DISCOVERY_SERVER#*:}" 2>/dev/null; then
        log_info "Rock64 robot and ROS2 discovery server are reachable"
        return 0
      fi
    fi
    
    sleep 2
    elapsed=$((elapsed + 2))
    log_debug "Still waiting for Rock64 robot... (${elapsed}/${timeout}s)"
  done
  
  log_warn "Rock64 robot not fully reachable within ${timeout}s, starting anyway"
  return 0  # Don't fail, ROS2 will handle reconnection
}

# ---------------------------------------------------------------------------
# Controller detection functions (PS5 priority)
# ---------------------------------------------------------------------------
detect_ps5_controller() {
  log_info "Detecting PS5 DualSense controller"
  
  local controller_found=false
  local controller_path=""
  local controller_name=""
  
  # Method 1: Use evdev-list if available (most reliable)
  if command -v evdev-list >/dev/null 2>&1; then
    log_debug "Using evdev-list for controller detection"
    while IFS= read -r line; do
      if echo "$line" | grep -qi "DualSense\|Sony.*Wireless\|PS5"; then
        controller_found=true
        controller_path=$(echo "$line" | awk '{print $1}')
        controller_name=$(echo "$line" | cut -d'"' -f2)
        log_info "Found PS5 controller via evdev-list: $controller_name at $controller_path"
        break
      fi
    done < <(evdev-list 2>/dev/null)
  fi
  
  # Method 2: Check /dev/input devices with udevadm
  if [[ "$controller_found" == "false" ]]; then
    log_debug "Checking /dev/input devices with udevadm"
    for device in /dev/input/event*; do
      if [[ -e "$device" ]]; then
        local device_info
        device_info=$(udevadm info --name="$device" 2>/dev/null || true)
        
        if echo "$device_info" | grep -qi "DualSense\|Sony.*Wireless\|PS5\|Guitar\|Wireless Controller"; then
          controller_found=true
          controller_path="$device"
          controller_name=$(echo "$device_info" | grep "ID_MODEL=" | cut -d= -f2 || echo "Unknown")
          log_info "Found PS5 controller via udevadm: $controller_name at $controller_path"
          break
        fi
      fi
    done
  fi
  
  # Method 3: Check /proc/bus/input/devices
  if [[ "$controller_found" == "false" ]]; then
    log_debug "Checking /proc/bus/input/devices"
    while IFS= read -r line; do
      if echo "$line" | grep -qi "DualSense\|Sony.*Wireless\|PS5"; then
        controller_found=true
        controller_name=$(echo "$line" | sed 's/Name=//')
        log_info "Found PS5 controller via /proc/bus/input/devices: $controller_name"
        break
      fi
    done < <(grep -i "Name=" /proc/bus/input/devices 2>/dev/null)
  fi
  
  # Method 4: Use lsusb to check for USB connection
  if [[ "$controller_found" == "false" ]]; then
    log_debug "Checking USB devices with lsusb"
    if command -v lsusb >/dev/null 2>&1; then
      while IFS= read -r line; do
        if echo "$line" | grep -qi "Sony\|PlayStation\|DualSense"; then
          controller_found=true
          controller_name=$(echo "$line")
          log_info "Found PS5 controller via lsusb: $controller_name"
          break
        fi
      done < <(lsusb 2>/dev/null)
    fi
  fi
  
  # Method 5: Try to open joystick device directly
  if [[ "$controller_found" == "false" ]]; then
    log_debug "Attempting to open joystick devices directly"
    for js_device in /dev/input/js*; do
      if [[ -e "$js_device" ]]; then
        if timeout 1 dd if="$js_device" of=/dev/null count=1 bs=8 2>/dev/null; then
          controller_found=true
          controller_path="$js_device"
          controller_name=$(basename "$js_device")
          log_info "Found active joystick device: $controller_name at $controller_path"
          break
        fi
      fi
    done
  fi
  
  if [[ "$controller_found" == "true" ]]; then
    echo "$controller_path"
    return 0
  else
    log_warn "No PS5 controller detected"
    return 1
  fi
}

wait_for_ps5_controller() {
  local timeout="${1:-$CONTROLLER_DETECTION_TIMEOUT}"
  log_info "Waiting for PS5 controller (timeout: ${timeout}s)"
  
  local elapsed=0
  while [[ $elapsed -lt $timeout ]]; do
    if detect_ps5_controller >/dev/null 2>&1; then
      local controller_path
      controller_path=$(detect_ps5_controller)
      log_info "PS5 controller detected at $controller_path"
      echo "$controller_path"
      return 0
    fi
    
    sleep 2
    elapsed=$((elapsed + 2))
    log_debug "Still waiting for PS5 controller... (${elapsed}/${timeout}s)"
  done
  
  log_error "PS5 controller not detected within ${timeout}s"
  return 1
}

verify_controller_accessibility() {
  local controller_path="$1"
  log_info "Verifying controller accessibility at $controller_path"
  
  # Try to read from the controller to verify it's accessible
  if timeout 3 python3 -c "
import sys
try:
    import evdev
    device = evdev.InputDevice('$controller_path')
    # Try to read capabilities
    caps = device.capabilities()
    print(f'Controller accessible: {device.name}')
    print(f'Capabilities: {len(caps)} event types')
    device.close()
    sys.exit(0)
except ImportError:
    print('evdev not installed, skipping verification')
    sys.exit(0)
except Exception as e:
    print(f'Controller not accessible: {e}')
    sys.exit(1)
" 2>/dev/null; then
    log_info "Controller verified accessible"
    return 0
  else
    log_warn "Controller verification failed, but will attempt startup anyway"
    return 0  # Don't fail, the ROS2 node will handle accessibility issues
  fi
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
    workspace="$SCRIPT_DIR/.."
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
# Main startup sequence
# ---------------------------------------------------------------------------
main() {
  log_info "=== Rock64 PC Operator Systemd Startup ==="
  log_info "Starting as user: $(whoami)"
  
  # Load configuration
  load_config
  
  # Determine service user
  if [[ -z "$SERVICE_USER" ]]; then
    SERVICE_USER="$(whoami)"
  fi
  log_info "Service user: $SERVICE_USER"
  
  # Wait for network
  if ! wait_for_network; then
    log_error "Failed to wait for network, aborting startup"
    exit 1
  fi
  
  # Wait for Rock64 robot
  wait_for_robot
  
  # Setup ROS2 environment
  if ! setup_ros2_environment; then
    log_error "Failed to setup ROS2 environment, aborting startup"
    exit 1
  fi
  
  # PS5 Controller Detection (PRIORITY)
  local controller_type=""
  local controller_path=""
  
  log_info "=== PS5 Controller Detection (PRIORITY) ==="
  
  if wait_for_ps5_controller; then
    controller_path=$(wait_for_ps5_controller)
    verify_controller_accessibility "$controller_path"
    controller_type="ps5"
    log_info "PS5 controller detected and verified, using PS5 teleop"
  elif [[ "$FALLBACK_TO_KEYBOARD" == "true" ]]; then
    log_warn "PS5 controller not detected, falling back to keyboard teleop"
    controller_type="keyboard_servo"
  else
    log_error "PS5 controller not detected and FALLBACK_TO_KEYBOARD=false, aborting startup"
    exit 1
  fi
  
  # Launch ROS2 teleop
  log_info "Launching ROS2 teleop node"
  log_info "Configuration: mode=$controller_type, robot=$ROBOT_HOST, namespace=$ROBOT_NAMESPACE"
  
  # Build launch command
  local launch_args=(
    "--role" "pc"
    "--workspace" "$WORKSPACE_PATH"
    "--robot-host" "$ROBOT_HOST"
    "--namespace" "$ROBOT_NAMESPACE"
    "--teleop-mode" "$controller_type"
    "--discovery-server" "$DISCOVERY_SERVER"
    "--domain-id" "$ROS_DOMAIN_ID"
    "--skip-build"
  )
  
  # Add controller-specific parameters
  if [[ "$controller_type" == "ps5" ]]; then
    launch_args+=("--joystick-index" "$JOYSTICK_INDEX")
    if [[ -n "$CONTROLLER_NAME" ]]; then
      launch_args+=("--controller-name" "$CONTROLLER_NAME")
    fi
  fi
  
  # Launch the operator
  log_info "Executing: ${SCRIPT_DIR}/../robot_start.sh ${launch_args[*]}"
  
  cd "$SCRIPT_DIR/.."
  exec ./robot_start.sh "${launch_args[@]}"
}

# Run main function
main "$@"
