#!/usr/bin/env bash
# =============================================================================
#  setup_mdns_rock64.sh  -  make the Rock64 reachable at <hostname>.local
#
#  Installs and enables Avahi (mDNS) on the Rock64 so other devices on the LAN
#  can reach it by name (e.g. `ssh rock64@rock64.local`, the LAN camera
#  re-stream at `http://rock64.local:8080/`) instead of a DHCP IP that can
#  change.
#
#  Run this ONCE on the Rock64:
#    ./setup_mdns_rock64.sh
#
#  It is idempotent - safe to re-run.
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 || fail "Run as root or install sudo."
  SUDO="sudo"
fi

if ! command -v apt-get >/dev/null 2>&1; then
  fail "This helper expects a Debian/Ubuntu system (apt-get). Install avahi-daemon manually otherwise."
fi

info "Installing avahi-daemon (mDNS responder)..."
$SUDO apt-get update -y
$SUDO apt-get install -y avahi-daemon

info "Enabling and starting avahi-daemon..."
if command -v systemctl >/dev/null 2>&1; then
  $SUDO systemctl enable avahi-daemon
  $SUDO systemctl restart avahi-daemon
else
  warn "systemctl not found; start avahi-daemon with your init system manually."
fi

HOSTNAME_SHORT="$(hostname)"
info "Done. This machine should now answer at: ${HOSTNAME_SHORT}.local"
echo ""
echo "From another device on the same WiFi, try:"
echo "  ping ${HOSTNAME_SHORT}.local"
echo "  ssh ${USER:-rock64}@${HOSTNAME_SHORT}.local"
echo ""
echo "If you started the camera re-stream (./robot_start.sh --stream-port 8080),"
echo "open it at:  http://${HOSTNAME_SHORT}.local:8080/"
