#!/bin/zsh
set -eu

PROJECT_DIR="/Users/josephnovotny/Documents/Codex/2026-08-17/referenced-chatgpt-conversation-this-is-an-2/work/NuttyPelicanEventAgent"
RUNTIME_DIR="/Users/josephnovotny/Library/Application Support/NuttyPelicanEventAgent"
LAUNCH_AGENT_DIR="/Users/josephnovotny/Library/LaunchAgents"
USER_DOMAIN="gui/$(id -u)"

mkdir -p "$RUNTIME_DIR"
rsync -a --delete --exclude='.git/' --exclude='instance/' --exclude='.env' "$PROJECT_DIR/" "$RUNTIME_DIR/"
if [[ ! -f "$RUNTIME_DIR/.env" ]]; then
  cp "$PROJECT_DIR/.env" "$RUNTIME_DIR/.env"
fi
mkdir -p "$RUNTIME_DIR/instance"
if [[ ! -f "$RUNTIME_DIR/instance/events.db" ]]; then
  cp -R "$PROJECT_DIR/instance/." "$RUNTIME_DIR/instance/"
fi
chmod 755 "$RUNTIME_DIR/scripts/run-worker.sh" "$RUNTIME_DIR/scripts/run-web.sh"

mkdir -p "$LAUNCH_AGENT_DIR"
install -m 644 "$RUNTIME_DIR/config/com.nuttypelican.event-agent.worker.plist" "$LAUNCH_AGENT_DIR/com.nuttypelican.event-agent.worker.plist"
install -m 644 "$RUNTIME_DIR/config/com.nuttypelican.event-agent.web.plist" "$LAUNCH_AGENT_DIR/com.nuttypelican.event-agent.web.plist"

launchctl bootout "$USER_DOMAIN/com.nuttypelican.event-agent.worker" 2>/dev/null || true
launchctl bootout "$USER_DOMAIN/com.nuttypelican.event-agent.web" 2>/dev/null || true
launchctl bootstrap "$USER_DOMAIN" "$LAUNCH_AGENT_DIR/com.nuttypelican.event-agent.worker.plist"
launchctl bootstrap "$USER_DOMAIN" "$LAUNCH_AGENT_DIR/com.nuttypelican.event-agent.web.plist"

echo "Nutty Pelican background services installed and started."
echo "Dashboard: http://127.0.0.1:5001"
