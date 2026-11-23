#!/usr/bin/env bash
# ตั้งเครื่องให้ ChatGPT Codex (หรือ agent อื่น) รันสคริปต์และทดสอบของ repo นี้ได้
# ใช้ในช่อง "Setup script" ของ environment ใน Codex:  bash scripts/codex-setup.sh
set -euo pipefail
SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  $SUDO apt-get update -y -qq && $SUDO apt-get install -y -qq ffmpeg
fi
PKGS="numpy pillow pytest opencv-python-headless"
python3 -m pip install -q $PKGS 2>/dev/null || python3 -m pip install -q --break-system-packages $PKGS
python3 -m py_compile .claude/skills/*/scripts/*.py
echo "พร้อมแล้ว: $(ffmpeg -version | head -1 | cut -d' ' -f1-3) · $(python3 --version)"
