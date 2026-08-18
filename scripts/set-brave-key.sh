#!/bin/zsh
set -eu

RUNTIME_ENV="/Users/josephnovotny/Library/Application Support/NuttyPelicanEventAgent/.env"
if [[ ! -f "$RUNTIME_ENV" ]]; then
  echo "Live agent configuration was not found. Run install-macos-services.sh first."
  exit 1
fi

read -rs "BRAVE_KEY?Paste the Brave Search API key, then press Return: "
echo
if [[ -z "$BRAVE_KEY" ]]; then
  echo "No key entered; nothing changed."
  exit 1
fi

TEMP_ENV="$(mktemp)"
chmod 600 "$TEMP_ENV"
FOUND=false
while IFS= read -r LINE || [[ -n "$LINE" ]]; do
  if [[ "$LINE" == BRAVE_SEARCH_API_KEY=* ]]; then
    print -r -- "BRAVE_SEARCH_API_KEY=$BRAVE_KEY" >> "$TEMP_ENV"
    FOUND=true
  else
    print -r -- "$LINE" >> "$TEMP_ENV"
  fi
done < "$RUNTIME_ENV"
if [[ "$FOUND" == false ]]; then
  print -r -- "BRAVE_SEARCH_API_KEY=$BRAVE_KEY" >> "$TEMP_ENV"
fi
mv "$TEMP_ENV" "$RUNTIME_ENV"
chmod 600 "$RUNTIME_ENV"
unset BRAVE_KEY
echo "Brave Search API key saved privately. Discovery remains disabled for supervised testing."
