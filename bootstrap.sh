#!/bin/bash
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
  echo 'Run this command as your normal user, without sudo.'
  exit 1
fi
if [ "$(uname -s)" != Linux ]; then
  echo 'This installer targets Linux desktops.'
  exit 1
fi
export PATH="$HOME/.local/bin:$PATH"
missing=()
command -v restic >/dev/null 2>&1 || missing+=(restic)
command -v age >/dev/null 2>&1 || missing+=(age)
command -v git >/dev/null 2>&1 || missing+=(git)
if command -v pacman >/dev/null 2>&1; then
  family=arch
  command -v gh >/dev/null 2>&1 || missing+=(github-cli)
  command -v python3 >/dev/null 2>&1 || missing+=(python)
elif command -v apt-get >/dev/null 2>&1; then
  family=apt
  command -v gh >/dev/null 2>&1 || missing+=(gh)
  command -v python3 >/dev/null 2>&1 || missing+=(python3)
else
  echo 'Supported: Omarchy/Arch and Ubuntu/Pop!_OS/Debian desktops.'
  exit 1
fi
if [ ${#missing[@]} -gt 0 ]; then
  echo 'Installing download tools. sudo may ask for your Linux login password.'
  if [ "$family" = arch ]; then
    if ! sudo pacman -S --needed --noconfirm "${missing[@]}"; then
      echo 'Package installation failed. Update Omarchy normally, then rerun this command.'
      exit 1
    fi
  else
    sudo apt-get update
    sudo apt-get install -y ca-certificates "${missing[@]}"
  fi
fi
task_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
python3 "$task_dir/ensure-restic.py"
restore_args=()
install_apps=1
for arg in "$@"; do
  if [ "$arg" = --skip-apps ]; then install_apps=0; else restore_args+=("$arg"); fi
done
python3 "$task_dir/bootstrap-restore.py" "${restore_args[@]}"
if [ "$install_apps" -eq 1 ]; then
  printf "\nInstalling your selected Linux applications…\n"
  bash "$task_dir/install-apps.sh"
fi
