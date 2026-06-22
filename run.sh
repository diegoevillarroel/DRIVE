#!/bin/bash
# DRIVE — Launch script for Windows/MSYS2/Git Bash
# Usage: ./run.sh [port]

PORT="${1:-8765}"
HOST="${2:-127.0.0.1}"

cd "$(dirname "$0")"
echo "Starting DRIVE on http://$HOST:$PORT"
python drive_main.py --host "$HOST" --port "$PORT"