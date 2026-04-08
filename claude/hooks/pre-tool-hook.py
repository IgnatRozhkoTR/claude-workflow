#!/usr/bin/env python3
"""PreToolUse hook: enforces phase gates, scope restrictions, and security boundaries.

Calls the Flask admin panel API for workspace/phase/scope decisions.
Handles security checks (bypass prevention) locally — no API needed.
"""
import json
import sys
import re
import os
from pathlib import Path

API_BASE = "http://localhost:5111"


def _resolve_governed_repo_root() -> Path:
    """Return the governed-workflow repo root without importing admin-panel packages.

    Resolution order:
    1. GOVERNED_WORKFLOW_REPO env var (absolute path).
    2. Walk parents of this file looking for a directory that contains both
       admin-panel/ and claude/hooks/.
    3. Fallback: two levels up from this file (claude/hooks/../.. == repo root).
    """
    env_root = os.environ.get("GOVERNED_WORKFLOW_REPO", "")
    if env_root:
        return Path(env_root).resolve()

    this_file = Path(__file__).resolve()
    for parent in this_file.parents:
        if (parent / "admin-panel").is_dir() and (parent / "claude" / "hooks").is_dir():
            return parent

    return this_file.parent.parent


_GOVERNED_REPO_ROOT = _resolve_governed_repo_root()
_ADMIN_PANEL_DIR = _GOVERNED_REPO_ROOT / "admin-panel"

def deny(reason):
    full_reason = reason + " Do NOT bypass hooks — ask the user to adjust scope or phase via the admin panel."
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": full_reason
        }
    }, sys.stdout)
    sys.exit(0)

def update_command(new_command):
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"command": new_command}
        }
    }, sys.stdout)
    sys.exit(0)

def allow():
    sys.exit(0)

def api_check(data):
    """Call the Flask API for permission check."""
    import urllib.request
    import urllib.error

    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        API_BASE + "/api/hook/check-permission",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        # If API is down, fail open (allow) — same behavior as ungoverned
        return {"governed": False, "allowed": True}

# ─── MAIN ───

data = json.load(sys.stdin)
tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})
cwd = data.get("cwd", ".")

# ─── LOCAL SECURITY CHECKS (must stay in hook, not API) ───

if tool_name == "Bash":
    command = tool_input.get("command", "")

    # Block curl/wget to admin panel
    if re.search(r'(curl|wget|http|fetch).*localhost:5111', command):
        deny("Direct HTTP requests to admin panel are blocked. Use MCP workspace tools.")

    # Block direct DB access
    if re.search(r'sqlite3.*admin-panel', command) or 'gate_nonce' in command:
        deny("Direct database access is blocked.")

    # Block curl to approve/reject endpoints
    if re.search(r'curl.*(approve|reject)', command):
        deny("Direct API calls to approve/reject are blocked. Use the admin panel UI.")

# ─── ALLOW ORCHESTRATOR METADATA WRITES ───

if tool_name in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
    file_path = tool_input.get("file_path", "")
    resolved_fp = Path(os.path.normpath(os.path.join(cwd, file_path))) if file_path else Path()
    is_claude_metadata = "/.claude/" in file_path
    is_worktrees_path = "/.claude/worktrees/" in file_path
    is_admin_panel_path = resolved_fp.is_relative_to(_ADMIN_PANEL_DIR)
    if is_claude_metadata and not is_worktrees_path and not is_admin_panel_path:
        allow()

# ─── ALLOW DOCKER COMMANDS ───

if tool_name == "Bash":
    command = tool_input.get("command", "")
    if re.match(r'\s*(docker|docker-compose|podman)\s', command):
        allow()

# ─── API CHECK FOR WORKSPACE/PHASE/SCOPE ───

request_data = {
    "cwd": cwd,
    "tool_name": tool_name,
}

if tool_name in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
    file_path = tool_input.get("file_path", "")
    # Canonicalize path
    if file_path and not os.path.isabs(file_path):
        file_path = os.path.join(cwd, file_path)
    request_data["file_path"] = os.path.normpath(file_path) if file_path else ""

if tool_name == "Bash":
    request_data["command"] = tool_input.get("command", "")

if tool_name and tool_name.startswith("mcp"):
    request_data["command"] = tool_name  # Pass MCP tool name as command for MR checks

result = api_check(request_data)

if not result.get("governed", False):
    allow()

if result.get("updated_command"):
    update_command(result["updated_command"])

if result.get("allowed", True):
    allow()
else:
    deny(result.get("reason", "Operation not allowed in current phase."))
