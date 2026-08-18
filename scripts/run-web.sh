#!/bin/zsh
set -eu

PROJECT_DIR="/Users/josephnovotny/Documents/Codex/2026-08-17/referenced-chatgpt-conversation-this-is-an-2/work/NuttyPelicanEventAgent"
cd "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/flask" --app run.py run --host 127.0.0.1 --port 5001
