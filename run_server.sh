#!/bin/bash
# run_server.sh — quick start AVA server

cd "$(dirname "$0")/server"

if [ ! -d "venv" ]; then
    echo "[AVA] Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo "[AVA] Starting server..."
python ava_server.py