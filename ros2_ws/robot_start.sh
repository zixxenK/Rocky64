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
#    --camera-ip    <ip>                Camera IP address (default: 192.168.0.152)
#    --camera-port  <port>              Camera port     (default: 80)
#    --serial-port  <path>              Serial device   (default: /dev/ttyACM0)
#    --baud-rate    <baud>              Serial baud     (default: 115200)
#    --namespace    <name>              Robot namespace (default: rock64_1)
#    --teleop-mode  <keyboard_servo|ps5>  Teleop mode for PC role (default: keyboard_servo)
#    --network-mode <station|ap>        Network mode    (default: station)
#    --expected-ssid <ssid>             Expected WiFi SSID (default: TELUS4424)
#    --robot-host   <ip>                Robot IP (required for --role pc)
#    --domain-id    <id>                ROS_DOMAIN_ID   (default: 0)
#    --skip-build                       Skip colcon build
#    --skip-preflight                   Skip Python preflight checks
#    --help
#
#  Examples:
#    # Rock64 (robot side):
#    ./robot_start.sh
#    ./robot_start.sh --camera-ip 192.168.0.153 --serial-port /dev/ttyUSB0
#
#    # PC operator side:
#    ./robot_start.sh --role pc --robot-host 192.168.0.110 --teleop-mode ps5
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
# fail() prints a clean message and exits; disable the ERR trap so the
# generic fatal banner doesn't fire on top of an already-explained error.
fail()  { trap - ERR; echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' not found in PATH.${2:+  $2}"
}

# Track the current phase so unexpected failures report where they happened.
CURRENT_STEP="initialising"
on_error() {
  local exit_code=$?
  local line="${1:-?}"
  trap - ERR
  echo "" >&2
  echo -e "${RED}==========================================================${NC}" >&2
  echo -e "${RED}[FATAL] Startup failed during: ${CURRENT_STEP}${NC}" >&2
  echo -e "${RED}        exit code ${exit_code} (line ${line})${NC}" >&2
  echo -e "${RED}        command: ${BASH_COMMAND}${NC}" >&2
  echo -e "${RED}==========================================================${NC}" >&2
  echo "Tips:" >&2
  echo "  - Build problems?     re-run with --skip-build (after a good build)" >&2
  echo "  - Preflight problems? re-run with --skip-preflight" >&2
  echo "  - See all options:    ./robot_start.sh --help" >&2
  exit "$exit_code"
}
trap 'on_error $LINENO' ERR

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
CAMERA_IP="192.168.1.153"
CAMERA_PORT="80"
SERIAL_PORT="/dev/ttyUSB0"
BAUD_RATE="115200"
ROBOT_NAMESPACE="rock64_1"
TELEOP_MODE="keyboard_servo"
NETWORK_MODE="station"
EXPECTED_SSID="TELUS4424"
ROBOT_HOST=""
DOMAIN_ID="0"
SKIP_BUILD="0"
SKIP_PREFLIGHT="0"

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
    --domain-id)      DOMAIN_ID="${2:-}";      shift 2 ;;
    --skip-build)     SKIP_BUILD="1";          shift ;;
    --skip-preflight) SKIP_PREFLIGHT="1";      shift ;;
    --help|-h)
      sed -n '/^#  Usage/,/^# ====/p' "$0" | sed 's/^# \{0,2\}//'
      exit 0
      ;;
    *) fail "Unknown argument: $1" ;;
  esac
done

# ---------------------------------------------------------------------------
# Validate args
# ---------------------------------------------------------------------------
[[ "$ROLE" == "rock64" || "$ROLE" == "pc" ]] || fail "--role must be rock64 or pc"
[[ "$NETWORK_MODE" == "station" || "$NETWORK_MODE" == "ap" ]] || fail "--network-mode must be station or ap"
if [[ "$ROLE" == "pc" && -z "$ROBOT_HOST" ]]; then
  fail "--robot-host is required for --role pc  (e.g. --robot-host 192.168.0.110)"
fi
if [[ "$NETWORK_MODE" == "ap" && -z "$CAMERA_IP" ]]; then
  CAMERA_IP="192.168.4.1"
fi

# ---------------------------------------------------------------------------
# Auto-detect workspace if not supplied
# ---------------------------------------------------------------------------
_detect_workspace() {
  local candidates=(
    "$HOME/rock64_ros2_ws"
    "$HOME/ros2_ws"
    "$HOME/Rock64 Robot/ros2_ws"
    "/mnt/c/Desktop/Rock64 Robot/ros2_ws"
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
info "Camera    : $CAMERA_IP:$CAMERA_PORT"
[[ "$ROLE" == "rock64" ]] && info "Serial    : $SERIAL_PORT @ ${BAUD_RATE} baud"
[[ "$ROLE" == "pc"     ]] && info "Teleop    : $TELEOP_MODE"
echo ""

# ---------------------------------------------------------------------------
# STEP 1 — Sanity-check the environment
# ---------------------------------------------------------------------------
CURRENT_STEP="[1/7] checking prerequisites"
info "[1/7] Checking prerequisites"

require_cmd python3 "Install with: sudo apt install python3"
[[ -f /opt/ros/foxy/setup.bash ]] || fail "ROS 2 Foxy not found at /opt/ros/foxy/setup.bash. Install ROS 2 Foxy first."
[[ -d "$WORKSPACE" ]]             || fail "Workspace not found: $WORKSPACE"
[[ -d "$WORKSPACE/src" ]]         || fail "Workspace missing src/: $WORKSPACE"
if [[ "$SKIP_BUILD" != "1" ]]; then
  require_cmd colcon "Install with: sudo apt install python3-colcon-common-extensions"
fi

# Warn about legacy ROS cruft in .bashrc
if grep -En '^(source|\.)[^#]*(noetic|melodic|catkin_ws|ROS_DISTRO)' \
     "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" 2>/dev/null | grep -q .; then
  warn "Your shell startup files appear to source an old ROS1/catkin overlay."
  warn "This can contaminate interactive shells. Run ./fix_bashrc_ros_overlay.sh"
  warn "on the Rock64 to clean it up (backups are made automatically)."
  echo ""
fi

# ---------------------------------------------------------------------------
# STEP 2 — Scrub the ROS environment
# ---------------------------------------------------------------------------
CURRENT_STEP="[2/7] scrubbing ROS environment"
info "[2/7] Scrubbing stale ROS environment variables"

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
CURRENT_STEP="[3/7] sourcing ROS 2 Foxy"
info "[3/7] Sourcing /opt/ros/foxy/setup.bash"

set +u
source /opt/ros/foxy/setup.bash
set -u

[[ "${ROS_DISTRO:-}" == "foxy" ]] || \
  fail "ROS_DISTRO is '${ROS_DISTRO:-<unset>}' after sourcing Foxy — start a fresh shell."

require_cmd ros2 "ROS 2 Foxy may be misinstalled — reinstall ros-foxy-ros-base."

python3 -c 'import ament_package' >/dev/null 2>&1 || \
  fail "ament_package not importable. Run: sudo apt install ros-foxy-ament-python python3-ament-package"

# ---------------------------------------------------------------------------
# STEP 4 — Build (unless skipped)
# ---------------------------------------------------------------------------
cd "$WORKSPACE"

CURRENT_STEP="[4/7] building workspace (colcon)"
if [[ "$SKIP_BUILD" == "1" ]]; then
  info "[4/7] Skipping build (--skip-build)"
else
  info "[4/7] Building workspace (this may take a minute…)"

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
CURRENT_STEP="[5/7] sourcing workspace overlay"
info "[5/7] Sourcing workspace overlay"

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
CURRENT_STEP="[6/7] verifying package discovery"
info "[6/7] Verifying package discovery"

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
    _show_pkg_diag "$pkg"
    echo "AMENT_PREFIX_PATH=${AMENT_PREFIX_PATH:-}" >&2
    fail "$pkg is not discoverable after sourcing the workspace."
  fi
done
info "robot_bringup, robot_control, robot_description — all visible. ✓"

# ---------------------------------------------------------------------------
# STEP 7 — Run Python preflight (optional)
# ---------------------------------------------------------------------------
CURRENT_STEP="[7/7] running preflight checks"
export ROS_DOMAIN_ID="$DOMAIN_ID"
export ROS_LOCALHOST_ONLY=0

# Enable unicast DDS peer discovery (multicast is often blocked on WiFi)
_dds_xml="$(ros2 pkg prefix robot_control 2>/dev/null)/share/robot_control/config/fastdds_unicast.xml"
if [[ -f "$_dds_xml" ]]; then
  export FASTRTPS_DEFAULT_PROFILES_FILE="$_dds_xml"
  info "Discovery: unicast peers via $FASTRTPS_DEFAULT_PROFILES_FILE"
else
  warn "fastdds_unicast.xml not found — using default multicast discovery."
  warn "If the PC cannot see the robot's topics, create/install fastdds_unicast.xml."
fi

if [[ "$SKIP_PREFLIGHT" == "1" ]]; then
  info "[7/7] Skipping Python preflight (--skip-preflight)"
elif [[ -f "$WORKSPACE/host_control/bringup_preflight.py" ]]; then
  info "[7/7] Running Python preflight checks"

  PREFLIGHT_ARGS=(
    --role           "$ROLE"
    --network-mode   "$NETWORK_MODE"
    --camera-ip      "$CAMERA_IP"
    --camera-port    "$CAMERA_PORT"
    --expected-ssid  "$EXPECTED_SSID"
    --robot-namespace "$ROBOT_NAMESPACE"
  )
  if [[ "$ROLE" == "rock64" ]]; then
    PREFLIGHT_ARGS+=(--serial-port "$SERIAL_PORT")
  else
    PREFLIGHT_ARGS+=(--robot-host "$ROBOT_HOST")
  fi

  # Don't let a flaky camera/serial check kill startup via set -e; capture
  # the exit code and report it clearly instead.
  set +e
  python3 "$WORKSPACE/host_control/bringup_preflight.py" "${PREFLIGHT_ARGS[@]}"
  PREFLIGHT_RC=$?
  set -e
  if [[ "$PREFLIGHT_RC" -ne 0 ]]; then
    echo ""
    warn "Preflight reported problems (exit $PREFLIGHT_RC) — see [FAIL] lines above."
    warn "Fix the hardware/network issues, or re-run with --skip-preflight to launch anyway."
    fail "Aborting before launch due to preflight failure."
  fi
else
  info "[7/7] bringup_preflight.py not found — skipping preflight"
fi

# ---------------------------------------------------------------------------
# Hardware / input device checks (role-specific)
# ---------------------------------------------------------------------------
if [[ "$ROLE" == "rock64" ]]; then
  if [[ ! -e "$SERIAL_PORT" ]]; then
    warn "Serial device not found at $SERIAL_PORT"
    warn "Detected candidates:"
    ls -1 /dev/ttyACM* /dev/ttyUSB* /dev/serial/by-id/* 2>/dev/null || warn "(none found)"
    warn "Pass --serial-port <device> if the path differs."
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

CURRENT_STEP="launching ros2 ($ROLE)"
banner "All checks passed — launching ($ROLE)"

if [[ "$ROLE" == "rock64" ]]; then
  info "Launch: rock64_bringup"
  info "  namespace : $ROBOT_NAMESPACE"
  info "  serial    : $SERIAL_PORT  ($BAUD_RATE baud)"
  info "  camera    : $CAMERA_URL"
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