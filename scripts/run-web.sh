#!/bin/zsh
set -eu

PROJECT_DIR="/Users/josephnovotny/Library/Application Support/NuttyPelicanEventAgent"
cd "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/flask" --app run.py run --host 127.0.0.1 --port 5001
