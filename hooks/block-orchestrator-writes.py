#!/usr/bin/env python3
"""PreToolUse hook: blocks file modifications by the main orchestrator.

Uses the `agent_id` field from hook input — present only when the hook fires
inside a sub-agent. If agent_id is absent, the main orchestrator is calling
the tool directly → deny. If present, a sub-agent is writing → allow.

Only enforces inside Git projects — outside Git, no restrictions apply.

Handles: Edit, Write, NotebookEdit (direct file tools)
         Bash (file-modifying commands: redirects, sed -i, cp, mv, rm, etc.)
"""
import json, sys, re, subprocess

data = json.load(sys.stdin)

# Only enforce inside Git projects — outside Git, no restrictions
try:
    subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=data.get("cwd", "."),
        capture_output=True, timeout=3
    ).check_returncode()
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name", "")

# Allow orchestrator to write to .claude/ paths (memory, settings, etc.)
# BUT NOT .claude/worktrees/ — those contain actual project code
if tool_name in ("Edit", "Write", "NotebookEdit"):
    file_path = data.get("tool_input", {}).get("file_path", "")
    if "/.claude/" in file_path and "/.claude/worktrees/" not in file_path:
        sys.exit(0)

# Allow all Docker commands (docker rm, docker cp, etc. match file-mod patterns)
if tool_name == "Bash":
    command = data.get("tool_input", {}).get("command", "")
    if re.match(r'\s*(docker|docker-compose|podman)\s', command):
        sys.exit(0)

# For Bash, only intercept file-modifying commands
if tool_name == "Bash":
    command = data.get("tool_input", {}).get("command", "")
    FILE_MOD_PATTERN = re.compile(
        r'(?<!\d\s)>\s|>>\s|\btee\s|\bdd\s.*\bof=|sed\s+-i|perl\s+-i'
        r'|python3?\s.*open\(|python3?\s.*write_text|python3?\s.*write_bytes|python3?\s.*Path\('
        r'|python3?\s*<<|echo\s.*\|\s*python3?'
        r'|ruby\s+-e.*File'
        r'|\bcp\s|\bmv\s|\brm\s|\brmdir\s|\bln\s'
        r'|\bchmod\s|\bchown\s|\btruncate\s|\bpatch\s'
        r'|\bfind\s.*-delete|\bfind\s.*-exec\s+rm'
        r'|install\s+-'
    )
    if not FILE_MOD_PATTERN.search(command):
        sys.exit(0)

# agent_id is present ONLY inside sub-agents (per Claude Code docs)
if data.get("agent_id"):
    sys.exit(0)

# Main orchestrator trying to modify files — deny
json.dump({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "Main orchestrator must NOT modify files directly. "
            "Delegate file modifications to sub-agents. "
            "Use the Agent tool to spawn a sub-agent for implementation work. "
            "Do NOT bypass hooks — this is a strict requirement set by the user."
        )
    }
}, sys.stdout)

sys.exit(0)
