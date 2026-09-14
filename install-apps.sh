#!/bin/bash
set -euo pipefail
if [ "$(uname -s)" != Linux ]; then
  echo 'Run this on your Linux laptop, not on the Mac.'
  exit 1
fi
if [ "$(id -u)" -eq 0 ]; then
  echo 'Run as your normal user, without sudo.'
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  if [ "${1:-}" = --plan ]; then
    echo 'Python 3 is needed to display the plan.'
    exit 1
  fi
  if command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm python
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3
  else
    echo 'Supported: Omarchy/Arch or Ubuntu/Pop!_OS/Debian.'
    exit 1
  fi
fi
task_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$task_dir/install-apps.py" "$@"
