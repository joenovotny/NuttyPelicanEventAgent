#!/bin/zsh
set -eu

PROJECT_DIR="/Users/josephnovotny/Library/Application Support/NuttyPelicanEventAgent"
cd "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/python" -m flask --app run.py automation-worker
