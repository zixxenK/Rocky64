#!/usr/bin/env bash
set -euo pipefail

FILES=("$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile")
LEGACY_DISTROS='noetic|melodic|kinetic|indigo|jade|hydro|lunar|ardent|bouncy|crystal|dashing|eloquent|rolling'

function process_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    return
  fi

  local backup="${file}.ros_cleanup.$(date +%Y%m%d%H%M%S).bak"
  cp "$file" "$backup"
  echo "Backed up $file -> $backup"
  echo "Scanning $file for old ROS overlay and catkin workspace sourcing lines..."

  python3 - <<PY
import re
from pathlib import Path

path = Path(r"${file}")
text = path.read_text()
lines = text.splitlines()
changed = []
patterns = [
    re.compile(r'^\s*(source|\.)\s+.*(/opt/ros/(${LEGACY_DISTROS})/setup\.(bash|sh)).*$', re.IGNORECASE),
    re.compile(r'^\s*(source|\.)\s+.*(\$HOME|~)?/catkin_ws/.*$', re.IGNORECASE),
    re.compile(r'^\s*(export\s+)?ROS_DISTRO\s*=\s*(${LEGACY_DISTROS})\b.*$', re.IGNORECASE),
    re.compile(r'^\s*(export\s+)?(ROS_PACKAGE_PATH|AMENT_PREFIX_PATH|ROS_ROOT|ROS_ETC_DIR|PYTHONPATH)\s*=.*(/opt/ros/(${LEGACY_DISTROS})|catkin_ws).*$', re.IGNORECASE),
]

out_lines = []
for idx, line in enumerate(lines, start=1):
    stripped = line.lstrip()
    if stripped.startswith('#'):
        out_lines.append(line)
        continue
    matched = False
    for pat in patterns:
        if pat.search(line):
            out_lines.append('# ' + line)
            changed.append((idx, line))
            matched = True
            break
    if not matched:
        out_lines.append(line)

if changed:
    path.write_text('\n'.join(out_lines) + '\n')
    print('Commented out the following lines:')
    for idx, line in changed:
        print(f'{idx}: {line}')
else:
    print('No legacy ROS or catkin workspace sourcing lines found.')
PY
}

for file in "${FILES[@]}"; do
  process_file "$file"
done

echo
if grep -En '^(source|\.)[^#]*(noetic|melodic|kinetic|catkin_ws)|ROS_DISTRO.*(noetic|melodic|kinetic)' "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" 2>/dev/null >/dev/null; then
  echo "WARNING: Some stale ROS overlay lines may still remain in your shell startup files."
  echo "Review ~/.bashrc, ~/.bash_profile, and ~/.profile manually."
else
  echo "Cleanup complete: stale ROS1/noetic and catkin_ws source lines were commented out."
fi

echo
echo "After this, start a fresh shell and verify with:"
echo "  env -i HOME=\"$HOME\" TERM=\"$TERM\" PATH=/usr/bin:/bin bash --noprofile --norc"
echo "  cd \"/home/rock64/Rocky64-new/ros2_ws\""
echo "  source /opt/ros/foxy/setup.bash"
echo "  source install/setup.bash"
echo "  ros2 pkg list | grep robot_control"
