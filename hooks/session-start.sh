#!/bin/bash
# SessionStart hook: register session + provide governed workflow context.
# Fires on: startup, resume, compact
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
SOURCE=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('source','startup'))" 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
  exit 0
fi

# Try to notify Flask server (fire and forget)
curl -s -X POST http://localhost:5111/api/hook/session-start \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"cwd\": \"$(pwd)\"}" \
  > /dev/null 2>&1 &

CWD=$(pwd)
DB_PATH="$HOME/.claude/admin-panel/server/admin-panel.db"

# Detect workspace for current directory
BRANCH=""
PHASE=""
WD=""
if [ -f "$DB_PATH" ]; then
  check_dir="$CWD"
  while [ "$check_dir" != "/" ]; do
    ws_row=$(sqlite3 "$DB_PATH" "SELECT branch, phase, working_dir FROM workspaces WHERE working_dir = '$check_dir' AND status = 'active' LIMIT 1;" 2>/dev/null)
    if [ -n "$ws_row" ]; then
      BRANCH=$(echo "$ws_row" | cut -d'|' -f1)
      PHASE=$(echo "$ws_row" | cut -d'|' -f2)
      WD=$(echo "$ws_row" | cut -d'|' -f3)
      break
    fi
    check_dir=$(dirname "$check_dir")
  done
fi

if [ -z "$BRANCH" ]; then
  exit 0
fi

# Build research listing from DB
RESEARCH_LIST=""
WS_ID=$(sqlite3 "$DB_PATH" "SELECT id FROM workspaces WHERE working_dir = '$WD' AND status = 'active' LIMIT 1;" 2>/dev/null)
if [ -n "$WS_ID" ]; then
  RESEARCH_LIST=$(sqlite3 "$DB_PATH" "SELECT '    - ' || topic || ' (' || CASE proven WHEN 1 THEN 'verified' WHEN -1 THEN 'rejected' ELSE 'pending' END || ')' FROM research_entries WHERE workspace_id = $WS_ID ORDER BY id;" 2>/dev/null)
fi

# Different message based on source
if [ "$SOURCE" = "compact" ]; then
  cat << REMINDER
═══════════════════════════════════════
SESSION RESTORED AFTER COMPACTION
Branch: $BRANCH | Phase: $PHASE

Your context was compacted. You MUST recover state before continuing:

1. Call workspace_get_state — get current phase, plan, scope, comments, and progress
   The progress field contains detailed records per phase: actions taken,
   obstacles hit, decisions made, and outcomes. This is your primary
   recovery source — read it fully before making any decisions.

2. Re-spawn the plan-advisor TEAMMATE (previous session teammates are gone):
   Agent(subagent_type: "co-pilot", model: "opus", run_in_background: true,
         prompt: "You are the plan-advisor teammate. Wait for instructions.")
   Store the agent ID — you need it for all future resume calls.

3. Research entries (details via workspace_get_research):
$RESEARCH_LIST

4. Check workspace_get_comments for any unresolved review feedback

After reading state, resume from phase $PHASE.
═══════════════════════════════════════
REMINDER
else
  cat << REMINDER
═══════════════════════════════════════════════════════════════
GOVERNED WORKFLOW — MANDATORY
Branch: $BRANCH | Phase: $PHASE
Run: /governed-workflow to read the full skill before starting.

Core rules:
1. You are the ORCHESTRATOR — coordinate only, never execute
2. NEVER read files, write code, or run commands yourself
3. ALWAYS delegate to sub-agents (researchers, engineers, validators)
4. Use MCP workspace tools for state management
5. Follow the phase progression — do not skip phases
6. User gates (2.1, 3.N.3, 4.2) require human approval

Recovery protocol (always do this first):
1. Call workspace_get_state — get phase, plan, scope, progress, and comments
   The progress field has detailed records per phase (actions, obstacles,
   decisions, outcomes). Read it to understand what has already been done.
2. Re-spawn the plan-advisor TEAMMATE if phase >= 1 (old teammates are gone):
   Agent(subagent_type: "co-pilot", model: "opus", run_in_background: true,
         prompt: "You are the plan-advisor teammate. Wait for instructions.")
3. Research entries (details via workspace_get_research):
$RESEARCH_LIST
4. Check workspace_get_comments for unresolved feedback
5. Resume from phase $PHASE
═══════════════════════════════════════════════════════════════
REMINDER
fi

exit 0
