#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Virtual environment missing. Run ./setup.sh first."
  exit 1
fi
if [ ! -f .env ]; then
  echo ".env missing. Run ./setup.sh and fill in .env."
  exit 1
fi
exec .venv/bin/python bot.py
