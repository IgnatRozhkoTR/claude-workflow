#!/bin/bash
# Admin Panel launcher — run directly or via shell alias
# Setup: chmod +x ~/.claude/admin-panel/start.sh

SERVER_DIR="$HOME/.claude/admin-panel/server"
LOG_FILE="/tmp/admin-panel.log"
PORT=5111

# Kill existing process on port
lsof -ti :$PORT | xargs kill -9 2>/dev/null
sleep 0.5

# Start server
cd "$SERVER_DIR" || { echo "ERROR: $SERVER_DIR not found"; exit 1; }
VENV_PYTHON="$HOME/.claude/admin-panel/.venv/bin/python3"
if [ -x "$VENV_PYTHON" ]; then
  nohup "$VENV_PYTHON" app.py > "$LOG_FILE" 2>&1 &
else
  nohup python3 app.py > "$LOG_FILE" 2>&1 &
fi
sleep 1.5

# Verify it started
if lsof -ti :$PORT > /dev/null 2>&1; then
  echo "Admin panel started at http://localhost:$PORT (log: $LOG_FILE)"
  open "http://localhost:$PORT" 2>/dev/null || echo "Open http://localhost:$PORT in your browser"
else
  echo "ERROR: Server failed to start. Check $LOG_FILE"
  tail -5 "$LOG_FILE"
  exit 1
fi
