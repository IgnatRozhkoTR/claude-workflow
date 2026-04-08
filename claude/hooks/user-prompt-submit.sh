#!/bin/bash
# UserPromptSubmit hook: governed workflow reminder on every message.

# Core orchestrator reminder
HINT="You are the orchestrator. You coordinate, sub-agents execute. Never edit files directly. Use workspace MCP tools. Run /governed-workflow if unsure."

# Local-only agent preference (not in SKILL.md to avoid push issues)
LOCAL_OVERRIDE="$HOME/.claude/local-agent-preference.txt"
if [ -f "$LOCAL_OVERRIDE" ]; then
    HINT="$HINT
$(cat "$LOCAL_OVERRIDE")"
fi

echo "$HINT"
exit 0
