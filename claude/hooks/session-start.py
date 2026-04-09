#!/usr/bin/env python3
"""Session start hook: registers session and prints context banner.

Calls the Flask admin panel API instead of querying SQLite directly.
"""
import json
import sys
import os
import urllib.request
import urllib.error
import threading

API_BASE = "http://localhost:5111"

data = json.load(sys.stdin)
session_id = data.get("session_id", "")
source = data.get("source", "")

if not session_id:
    sys.exit(0)

# ─── Register session (fire and forget) ───

def register_session():
    try:
        payload = json.dumps({"session_id": session_id, "cwd": data.get("cwd", os.getcwd())}).encode()
        req = urllib.request.Request(
            API_BASE + "/api/hook/session-start",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

threading.Thread(target=register_session, daemon=True).start()

# ─── Get context from API ───

cwd = data.get("cwd", os.getcwd())

try:
    req = urllib.request.Request(
        API_BASE + "/api/hook/session-context?cwd=" + urllib.request.pathname2url(cwd),
        method="GET"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        ctx = json.loads(resp.read())
except Exception:
    sys.exit(0)

if not ctx.get("found"):
    sys.exit(0)

branch = ctx.get("branch", "")
phase = ctx.get("phase", "0")
research = ctx.get("research", [])

# ─── Build and print banner ───

research_lines = ""
for r in research:
    status = "proven" if r.get("proven") == 1 else "rejected" if r.get("proven") == -1 else "pending"
    research_lines += f"  - {r['topic']} ({status})\n"

if source == "compact":
    banner = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXT RESTORATION — Governed Workflow
Branch: {branch} | Phase: {phase}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Session was compacted. Recovery steps:
1. Call workspace_get_state to read current phase and context
2. Read progress entries to understand what was completed
3. Re-spawn the plan-advisor teammate if phase > 0
4. Continue from the current phase

{f"Research entries:\\n{research_lines}" if research_lines else ""}
"""
else:
    banner = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GOVERNED WORKFLOW SESSION
Branch: {branch} | Phase: {phase}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are the orchestrator. You coordinate, sub-agents execute.
Never edit files directly. Use workspace MCP tools.
Run /governed-workflow if unsure.

{f"Research entries:\\n{research_lines}" if research_lines else ""}
"""

print(banner.strip())
sys.exit(0)
