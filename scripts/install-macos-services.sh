#!/bin/zsh
set -eu

PROJECT_DIR="/Users/josephnovotny/Documents/Codex/2026-08-17/referenced-chatgpt-conversation-this-is-an-2/work/NuttyPelicanEventAgent"
LAUNCH_AGENT_DIR="/Users/josephnovotny/Library/LaunchAgents"
USER_DOMAIN="gui/$(id -u)"

mkdir -p "$LAUNCH_AGENT_DIR"
install -m 644 "$PROJECT_DIR/config/com.nuttypelican.event-agent.worker.plist" "$LAUNCH_AGENT_DIR/com.nuttypelican.event-agent.worker.plist"
install -m 644 "$PROJECT_DIR/config/com.nuttypelican.event-agent.web.plist" "$LAUNCH_AGENT_DIR/com.nuttypelican.event-agent.web.plist"

launchctl bootout "$USER_DOMAIN/com.nuttypelican.event-agent.worker" 2>/dev/null || true
launchctl bootout "$USER_DOMAIN/com.nuttypelican.event-agent.web" 2>/dev/null || true
launchctl bootstrap "$USER_DOMAIN" "$LAUNCH_AGENT_DIR/com.nuttypelican.event-agent.worker.plist"
launchctl bootstrap "$USER_DOMAIN" "$LAUNCH_AGENT_DIR/com.nuttypelican.event-agent.web.plist"

echo "Nutty Pelican background services installed and started."
echo "Dashboard: http://127.0.0.1:5001"
