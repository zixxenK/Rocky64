#!/usr/bin/env bash
# =============================================================================
#  robot_start.sh  —  One-shot Rock64 robot startup
#
#  Usage (Rock64 hardware side):
#    ./robot_start.sh [OPTIONS]
#
#  Options:
#    --role         <rock64|pc>         Which machine you're running on (default: rock64)
#    --workspace    <path>              Workspace root (auto-detected if omitted)
#    --camera-ip    <ip>                Camera IP address (default: 192.168.1.153 for station, 192.168.4.1 for AP)
#    --camera-port  <port>              Camera port     (default: 80)
#    --serial-port  <path>              Serial device   (auto-detected: /dev/ttyUSB0 or /dev/ttyACM0)
#    --baud-rate    <baud>              Serial baud     (default: 115200)
#    --namespace    <name>              Robot namespace (default: rock64_1)
#    --teleop-mode  <keyboard_servo|ps5>  Teleop mode for PC role (default: keyboard_servo)
#    --network-mode <station|ap>        Network mode    (default: auto-detect)
#    --expected-ssid <ssid>             Expected WiFi SSID (default: TELUS4424)
#    --robot-host   <ip>                Robot IP (default: 192.168.1.159)
#    --discovery-server <ip:port>      ROS 2 Discovery Server (default: 192.168.1.159:11811)
#    --domain-id    <id>                ROS_DOMAIN_ID   (default: 0)
#    --skip-build                       Skip colcon build
#    --help
#
#  Examples:
#    # Rock64 (robot side):
#    ./robot_start.sh
#    ./robot_start.sh --camera-ip 192.168.1.153 --serial-port /dev/ttyUSB0
#
#    # PC operator side:
#    ./robot_start.sh --role pc --robot-host 192.168.1.159 --teleop-mode ps5
# =============================================================================
set -eo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

banner() {
  echo ""
  echo "=========================================================="
  echo "  $*"
  echo "=========================================================="
  echo ""
}

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
ROLE="rock64"
WORKSPACE=""
CAMERA_IP=""  # Will be set based on network mode: 192.168.1.153 (station) or 192.168.4.1 (AP)
CAMERA_PORT="80"
SERIAL_PORT=""  # Will be auto-detected
BAUD_RATE="115200"
ROBOT_NAMESPACE="rock64_1"
TELEOP_MODE="keyboard_servo"
NETWORK_MODE="auto"  # Auto-detect based on WiFi availability
EXPECTED_SSID="TELUS4424"
ROBOT_HOST="192.168.1.159"
DISCOVERY_SERVER="192.168.1.159:11811"
DOMAIN_ID="0"
SKIP_BUILD="0"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --role)           ROLE="${2:-}";           shift 2 ;;
    --workspace)      WORKSPACE="${2:-}";      shift 2 ;;
    --camera-ip)      CAMERA_IP="${2:-}";      shift 2 ;;
    --camera-port)    CAMERA_PORT="${2:-}";    shift 2 ;;
    --serial-port)    SERIAL_PORT="${2:-}";    shift 2 ;;
    --baud-rate)      BAUD_RATE="${2:-}";      shift 2 ;;
    --namespace)      ROBOT_NAMESPACE="${2:-}"; shift 2 ;;
    --teleop-mode)    TELEOP_MODE="${2:-}";    shift 2 ;;
    --network-mode)   NETWORK_MODE="${2:-}";   shift 2 ;;
    --expected-ssid)  EXPECTED_SSID="${2:-}";  shift 2 ;;
    --robot-host)     ROBOT_HOST="${2:-}";     shift 2 ;;
    --discovery-server) DISCOVERY_SERVER="${2:-}"; shift 2 ;;
    --domain-id)      DOMAIN_ID="${2:-}";      shift 2 ;;
    --skip-build)     SKIP_BUILD="1";          shift ;;
    --help|-h)
      sed -n '/^#  Usage/,/^# ====/p' "$0" | sed 's/^# \{0,2\}//'
      exit 0
      ;;
    *) fail "Unknown argument: $1" ;;
  esac
done

# ---------------------------------------------------------------------------
# Auto-detection functions
# ---------------------------------------------------------------------------
_detect_network_mode() {
  # Auto-detect network mode based on WiFi availability
  if [[ "$NETWORK_MODE" != "auto" ]]; then
    echo "$NETWORK_MODE"
    return 0
  fi

  # Check if expected SSID is available
  if command -v nmcli >/dev/null 2>&1; then
    if nmcli -t -f ssid dev wifi | grep -q "^${EXPECTED_SSID}$"; then
      echo "station"
    else
      echo "ap"
    fi
  elif command -w iwlist >/dev/null 2>&1; then
    if iwlist scan 2>/dev/null | grep -q "${EXPECTED_SSID}"; then
      echo "station"
    else
      echo "ap"
    fi
  else
    # Default to station mode if we can't detect
    echo "station"
  fi
}

_detect_serial_port() {
  # Auto-detect serial port
  if [[ -n "$SERIAL_PORT" ]]; then
    echo "$SERIAL_PORT"
    return 0
  fi

  # Prefer USB0, fallback to ACM0
  if [[ -e "/dev/ttyUSB0" ]]; then
    echo "/dev/ttyUSB0"
  elif [[ -e "/dev/ttyACM0" ]]; then
    echo "/dev/ttyACM0"
  else
    # Try to find any Arduino/USB serial device
    for device in /dev/ttyUSB* /dev/ttyACM*; do
      if [[ -e "$device" ]]; then
        echo "$device"
        return 0
      fi
    done
    echo "/dev/ttyUSB0"  # Default fallback
  fi
}

# ---------------------------------------------------------------------------
# Auto-detect configuration
# ---------------------------------------------------------------------------
NETWORK_MODE="$(_detect_network_mode)"
SERIAL_PORT="$(_detect_serial_port)"

# Set camera IP based on network mode
if [[ -z "$CAMERA_IP" ]]; then
  if [[ "$NETWORK_MODE" == "station" ]]; then
    CAMERA_IP="192.168.1.153"  # Station mode camera IP
  else
    CAMERA_IP="192.168.4.1"    # AP mode camera IP
  fi
fi

# ---------------------------------------------------------------------------
# Validate args
# ---------------------------------------------------------------------------
[[ "$ROLE" == "rock64" || "$ROLE" == "pc" ]] || fail "--role must be rock64 or pc"
[[ "$NETWORK_MODE" == "station" || "$NETWORK_MODE" == "ap" ]] || fail "--network-mode must be station or ap"
if [[ "$ROLE" == "pc" && -z "$ROBOT_HOST" ]]; then
  fail "--robot-host is required for --role pc  (e.g. --robot-host 192.168.1.159)"
fi

# ---------------------------------------------------------------------------
# Auto-detect workspace if not supplied
# ---------------------------------------------------------------------------
_detect_workspace() {
  local candidates=(
    "/mnt/c/Desktop/Rock64 Robot/ros2_ws"      # WSL path
    "C:/Desktop/Rock64 Robot/ros2_ws"         # Windows Git Bash path
    "$HOME/Rock64 Robot/ros2_ws"              # Linux home
    "$HOME/ros2_ws"                           # Fallback
    "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"  # Script location
  )
  for c in "${candidates[@]}"; do
    if [[ -d "$c/src/robot_bringup" && -d "$c/src/robot_control" ]]; then
      echo "$c"; return 0
    fi
  done
  # fallback: directory containing this script
  echo "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
}

if [[ -z "$WORKSPACE" ]]; then
  WORKSPACE="$(_detect_workspace)"
fi

banner "Rock64 Robot — one-shot startup  (role=$ROLE)"
info "Workspace : $WORKSPACE"
info "Namespace : $ROBOT_NAMESPACE"
info "Network   : $NETWORK_MODE mode"
info "Camera    : $CAMERA_IP:$CAMERA_PORT"
[[ "$ROLE" == "rock64" ]] && info "Serial    : $SERIAL_PORT @ ${BAUD_RATE} baud"
[[ "$ROLE" == "pc"     ]] && info "Teleop    : $TELEOP_MODE"
[[ "$ROLE" == "pc"     ]] && info "Robot     : $ROBOT_HOST"
info "Discovery: $DISCOVERY_SERVER"
echo ""

# ---------------------------------------------------------------------------
# STEP 1 — Sanity-check the environment
# ---------------------------------------------------------------------------
info "[1/6] Checking prerequisites"

[[ -f /opt/ros/foxy/setup.bash ]] || fail "ROS 2 Foxy not found at /opt/ros/foxy/setup.bash"
[[ -d "$WORKSPACE" ]]             || fail "Workspace not found: $WORKSPACE"
[[ -d "$WORKSPACE/src" ]]         || fail "Workspace missing src/: $WORKSPACE"

# ---------------------------------------------------------------------------
# STEP 2 — Scrub the ROS environment
# ---------------------------------------------------------------------------
info "[2/6] Scrubbing stale ROS environment variables"

unset ROS_DISTRO ROS_VERSION ROS_PACKAGE_PATH ROS_MASTER_URI ROS_ROOT \
      AMENT_PREFIX_PATH COLCON_PREFIX_PATH COLCON_CURRENT_PREFIX \
      CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH ROS_ETC_DIR \
      ROSLISP_PACKAGE_DIRECTORIES ROS_LOCALHOST_ONLY ROS_PYTHON_VERSION \
      COLCON_TRACE 2>/dev/null || true

# Strip ROS path pollution from PATH
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export PATH

# ---------------------------------------------------------------------------
# STEP 3 — Source base ROS 2 Foxy
# ---------------------------------------------------------------------------
info "[3/6] Sourcing /opt/ros/foxy/setup.bash"

set +u
source /opt/ros/foxy/setup.bash
set -u

[[ "${ROS_DISTRO:-}" == "foxy" ]] || \
  fail "ROS_DISTRO is '${ROS_DISTRO:-<unset>}' after sourcing Foxy — start a fresh shell."

python3 -c 'import ament_package' >/dev/null 2>&1 || \
  fail "ament_package not importable. Run: sudo apt install ros-foxy-ament-python python3-ament-package"

# ---------------------------------------------------------------------------
# STEP 4 — Build (unless skipped)
# ---------------------------------------------------------------------------
cd "$WORKSPACE"

if [[ "$SKIP_BUILD" == "1" ]]; then
  info "[4/6] Skipping build (--skip-build)"
else
  info "[4/6] Building workspace (this may take a minute…)"

  # Remove stale artifacts so prefix files regenerate cleanly
  rm -rf "$WORKSPACE/build" "$WORKSPACE/install" "$WORKSPACE/log"

  colcon build \
    --symlink-install \
    --merge-install \
    --base-paths src

  # Verify package.dsv hooks exist
  for pkg in robot_bringup robot_control robot_description; do
    dsv="$WORKSPACE/install/share/$pkg/package.dsv"
    [[ -f "$dsv" ]] || fail "Missing package metadata: $dsv"
    grep -q 'ament_prefix_path' "$dsv" || \
      fail "$pkg package.dsv missing ament_prefix_path hook. Check $pkg/package.xml has <export><build_type>ament_python</build_type></export>"
  done

  info "Build complete."
fi

# ---------------------------------------------------------------------------
# STEP 5 — Source workspace overlay
# ---------------------------------------------------------------------------
info "[5/6] Sourcing workspace overlay"

if [[ ! -f "$WORKSPACE/install/setup.bash" ]]; then
  fail "install/setup.bash not found. Build first, or omit --skip-build."
fi

set +u
export COLCON_CURRENT_PREFIX="$WORKSPACE/install"
source /opt/ros/foxy/setup.bash
source "$WORKSPACE/install/setup.bash"
set -u

# Ensure our install dir is front-and-centre in AMENT_PREFIX_PATH
if [[ ":${AMENT_PREFIX_PATH:-}:" != *":$WORKSPACE/install:"* ]]; then
  export AMENT_PREFIX_PATH="$WORKSPACE/install:${AMENT_PREFIX_PATH:-}"
fi

# ---------------------------------------------------------------------------
# STEP 6 — Verify package discovery
# ---------------------------------------------------------------------------
info "[6/6] Verifying package discovery"

_show_pkg_diag() {
  local pkg="$1"
  local dsv="install/share/$pkg/package.dsv"
  warn "  Diagnostic for $pkg:"
  if [[ -f "$dsv" ]]; then
    if grep -q 'ament_prefix_path' "$dsv"; then
      warn "    package.dsv OK — hook present"
    else
      warn "    package.dsv MISSING ament_prefix_path hook"
      warn "    → add <export><build_type>ament_python</build_type></export> to $pkg/package.xml"
    fi
  else
    warn "    package.dsv not found at $dsv — rebuild the workspace"
  fi
}

for pkg in robot_bringup robot_control robot_description; do
  if ! ros2 pkg prefix "$pkg" >/dev/null 2>&1; then
    echo ""
    fail "$pkg is not discoverable after sourcing the workspace."
    _show_pkg_diag "$pkg"
    echo "AMENT_PREFIX_PATH=${AMENT_PREFIX_PATH:-}"
    exit 1
  fi
done
info "robot_bringup, robot_control, robot_description — all visible. ✓"

# ---------------------------------------------------------------------------
# Set ROS environment
# ---------------------------------------------------------------------------
export ROS_DOMAIN_ID="$DOMAIN_ID"
export ROS_DISCOVERY_SERVER="$DISCOVERY_SERVER"
export ROS_LOCALHOST_ONLY=0

# ---------------------------------------------------------------------------
# Hardware / input device checks (role-specific)
# ---------------------------------------------------------------------------
if [[ "$ROLE" == "rock64" ]]; then
  if [[ ! -e "$SERIAL_PORT" ]]; then
    warn "Serial device not found at $SERIAL_PORT"
    warn "Detected candidates:"
    ls -1 /dev/ttyACM* /dev/ttyUSB* /dev/serial/by-id/* 2>/dev/null || warn "(none found)"
    warn "Pass --serial-port <device> if the path differs."
    warn "Continuing anyway — serial bridge will attempt auto-detection..."
  fi
fi

if [[ "$ROLE" == "pc" && "$TELEOP_MODE" == "ps5" ]]; then
  echo ""
  warn "PS5 controller check:"
  if ls /dev/input/js* >/dev/null 2>&1; then
    info "  Joystick devices found:"
    ls -l /dev/input/js* 2>/dev/null
  else
    warn "  No /dev/input/js* devices found."
    warn "  If running under WSL, attach the controller via usbipd:"
    warn "    usbipd list"
    warn "    usbipd attach --wsl --busid <busid>"
  fi
fi

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
CAMERA_URL="http://${CAMERA_IP}:${CAMERA_PORT}/stream"
# Strip redundant :80 from URL for cleanliness
[[ "$CAMERA_PORT" == "80" ]] && CAMERA_URL="http://${CAMERA_IP}/stream"

# Important: For station mode, provide network guidance
if [[ "$NETWORK_MODE" == "station" && "$ROLE" == "rock64" ]]; then
  warn "IMPORTANT: ESP32 is configured for station mode (connects to WiFi router)"
  warn "Make sure ESP32 has connected to WiFi and obtained an IP address"
  warn "Check ESP32 serial monitor or router DHCP table for actual IP"
  warn "If camera fails, update camera-url in rock64_hardware.yaml with ESP32's actual IP"
  echo ""
fi

banner "All checks passed — launching ($ROLE)"

if [[ "$ROLE" == "rock64" ]]; then
  info "Launch: rock64_bringup"
  info "  namespace : $ROBOT_NAMESPACE"
  info "  serial    : $SERIAL_PORT  ($BAUD_RATE baud)"
  info "  camera    : $CAMERA_URL"
  info "  network   : $NETWORK_MODE mode"
  echo ""

  exec ros2 launch robot_bringup rock64_bringup.launch.py \
    robot_namespace:="$ROBOT_NAMESPACE" \
    serial_port:="$SERIAL_PORT" \
    baud_rate:="$BAUD_RATE" \
    camera_url:="$CAMERA_URL"

else
  info "Launch: operator_session"
  info "  namespace : $ROBOT_NAMESPACE"
  info "  teleop    : $TELEOP_MODE"
  info "  robot     : $ROBOT_HOST"
  echo ""

  if [[ "$TELEOP_MODE" == "ps5" ]]; then
    exec ros2 launch robot_bringup ps5_teleop.launch.py \
      robot_namespace:="$ROBOT_NAMESPACE" \
      joystick_index:=0 \
      controller_name:='' \
      leftx_axis:=0 \
      lefty_axis:=1 \
      rightx_axis:=2 \
      l2_axis:=4 \
      r2_axis:=5
  else
    exec ros2 launch robot_bringup operator_session.launch.py \
      robot_namespace:="$ROBOT_NAMESPACE" \
      teleop_mode:="$TELEOP_MODE"
  fi
fi
