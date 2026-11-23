#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3 is required."; exit 1; }
command -v ffmpeg >/dev/null || { echo "FFmpeg is required. Install with: sudo apt install ffmpeg"; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Edit it and add your keys before running ./run.sh."
else
  echo ".env already exists; leaving it unchanged."
fi
mkdir -p data
echo "Setup complete."
