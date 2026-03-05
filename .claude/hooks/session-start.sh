#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "=== RedTeam SessionStart Hook ==="

# --- Python dependencies ---
if [ -f "$CLAUDE_PROJECT_DIR/requirements.txt" ]; then
  echo "Installing Python dependencies..."
  pip install -r "$CLAUDE_PROJECT_DIR/requirements.txt" --quiet
fi

# --- Node dependencies ---
if [ -f "$CLAUDE_PROJECT_DIR/package.json" ]; then
  echo "Installing Node dependencies..."
  cd "$CLAUDE_PROJECT_DIR" && npm install --silent
fi

echo "=== Environment ready ==="
