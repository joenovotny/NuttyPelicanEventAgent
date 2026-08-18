#!/bin/zsh
set -eu

RUNTIME_ENV="/Users/josephnovotny/Library/Application Support/NuttyPelicanEventAgent/.env"
RUNTIME_DB="/Users/josephnovotny/Library/Application Support/NuttyPelicanEventAgent/instance/events.db"
USER_DOMAIN="gui/$(id -u)"

set_value() {
  local KEY="$1"
  local VALUE="$2"
  local TEMP_ENV="$(mktemp)"
  local FOUND=false
  chmod 600 "$TEMP_ENV"
  while IFS= read -r LINE || [[ -n "$LINE" ]]; do
    if [[ "$LINE" == "$KEY="* ]]; then
      print -r -- "$KEY=$VALUE" >> "$TEMP_ENV"
      FOUND=true
    else
      print -r -- "$LINE" >> "$TEMP_ENV"
    fi
  done < "$RUNTIME_ENV"
  if [[ "$FOUND" == false ]]; then
    print -r -- "$KEY=$VALUE" >> "$TEMP_ENV"
  fi
  mv "$TEMP_ENV" "$RUNTIME_ENV"
  chmod 600 "$RUNTIME_ENV"
}

set_value "DISCOVERY_ENABLED" "true"
set_value "DISCOVERY_AUTO_QUALIFY" "true"
set_value "DISCOVERY_INTERVAL_HOURS" "24"
set_value "BRAVE_MONTHLY_QUERY_LIMIT" "250"
set_value "RESEARCH_BATCH_SIZE" "10"
set_value "RESEARCH_MAX_ATTEMPTS" "3"
set_value "ALERT_EMAIL_ADDRESS" "joenovotny@me.com"

# Make the first enabled discovery/recheck run immediately.
"/Users/josephnovotny/Library/Application Support/NuttyPelicanEventAgent/.venv/bin/python" - "$RUNTIME_DB" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute("DELETE FROM automation_state WHERE key = 'last_discovery_at'")
PY

launchctl kickstart -k "$USER_DOMAIN/com.nuttypelican.event-agent.worker"
echo "Daily discovery, conservative auto-qualification, and Joe email alerts are enabled."
