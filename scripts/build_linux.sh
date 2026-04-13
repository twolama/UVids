#!/bin/bash

set -euo pipefail

if [[ ! -f "app/assets/ffmpeg/linux/ffmpeg" ]]; then
  echo "Missing app/assets/ffmpeg/linux/ffmpeg. Place the Linux FFmpeg binary there before building."
  exit 1
fi

chmod +x "app/assets/ffmpeg/linux/ffmpeg"

python3 -m PyInstaller --clean --noconfirm uvids.spec
