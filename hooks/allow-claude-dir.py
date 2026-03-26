#!/usr/bin/env python3
"""PreToolUse hook: auto-approve writes to .claude/ directory.
Bypasses the protected directory gate introduced in Claude Code v2.1.78.
"""
import json
import sys

data = json.load(sys.stdin)
tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})

file_path = tool_input.get("file_path", "")
command = tool_input.get("command", "")

is_claude_dir = "/.claude/" in file_path or file_path.endswith("/.claude")

if tool_name == "Bash" and "/.claude/" in command:
    is_claude_dir = True

if is_claude_dir:
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow"
        }
    }, sys.stdout)
    sys.exit(0)

sys.exit(0)
