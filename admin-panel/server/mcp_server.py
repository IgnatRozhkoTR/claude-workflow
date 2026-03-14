"""MCP server for workspace state management (stdio transport)."""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Add server/ to path for shared imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP
from db import get_db, init_db
from helpers import VALID_CRITERIA_TYPES, compute_phase_sequence
from i18n import t
from phase import Phase

# Initialize DB on import
init_db()

mcp = FastMCP("workspace", instructions="Workspace state management for orchestrator workflow.")


def _detect_workspace():
    """Auto-detect workspace from cwd by matching working_dir in DB. Prefers active over archived."""
    cwd = os.getcwd()
    db = get_db()
    try:
        ws = db.execute(
            "SELECT * FROM workspaces WHERE working_dir = ? ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, id DESC",
            (cwd,)
        ).fetchone()
        if ws:
            return ws, db.execute("SELECT * FROM projects WHERE id = ?", (ws["project_id"],)).fetchone()

        for parent in Path(cwd).parents:
            ws = db.execute(
                "SELECT * FROM workspaces WHERE working_dir = ? ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, id DESC",
                (str(parent),)
            ).fetchone()
            if ws:
                return ws, db.execute("SELECT * FROM projects WHERE id = ?", (ws["project_id"],)).fetchone()

        return None, None
    finally:
        db.close()


@mcp.tool()
def workspace_get_state() -> dict:
    """Get compact workspace state overview. Returns core state (phase, scope, context, discussions) inline,
    with summaries and counts for large sections.

    For full details, use dedicated tools:
    - Plan: workspace_get_plan
    - Progress details: workspace_get_progress
    - Research: workspace_list_research / workspace_get_research
    - Comments: workspace_get_comments
    - Review issues: workspace_get_review_issues
    - Criteria: workspace_get_criteria

    Does NOT return gate_nonce (security: only available via admin panel UI)."""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    scope = json.loads(ws["scope_json"]) if ws["scope_json"] else {}
    plan = json.loads(ws["plan_json"]) if ws["plan_json"] else {"description": "", "systemDiagram": "", "execution": []}
    phase_sequence = compute_phase_sequence(plan)

    context = {
        "ticket_id": ws["ticket_id"] or "",
        "ticket_name": ws["ticket_name"] or "",
        "context": ws["context_text"] or "",
        "file_references": json.loads(ws["context_refs_json"] or "[]"),
    }

    execution = plan.get("execution", [])

    current_subphase = None
    if ws["phase"].startswith("3.") and "." in ws["phase"][2:]:
        sub_id = ws["phase"].rsplit(".", 1)[0]
        current_subphase = next((item for item in execution if item.get("id") == sub_id), None)

    plan_summary = {
        "description": plan.get("description", ""),
        "execution_count": len(execution),
        "execution_names": [{"id": item["id"], "name": item["name"]} for item in execution],
    }
    if current_subphase:
        plan_summary["current_subphase"] = current_subphase

    db = get_db()
    try:
        progress_rows = db.execute(
            "SELECT phase, summary FROM progress_entries WHERE workspace_id = ? ORDER BY id",
            (ws["id"],)
        ).fetchall()
        progress_summary = {row["phase"]: row["summary"] for row in progress_rows}

        research_rows = db.execute(
            "SELECT id, topic, proven FROM research_entries WHERE workspace_id = ? ORDER BY id",
            (ws["id"],)
        ).fetchall()
        research_summary = [{"id": row["id"], "topic": row["topic"], "proven": row["proven"]} for row in research_rows]

        comment_count = db.execute(
            "SELECT COUNT(*) as cnt FROM discussions WHERE workspace_id = ? AND scope IS NOT NULL AND status = 'open'",
            (ws["id"],)
        ).fetchone()["cnt"]

        review_rows = db.execute(
            "SELECT resolution, COUNT(*) as cnt FROM review_issues WHERE workspace_id = ? GROUP BY resolution",
            (ws["id"],)
        ).fetchall()
        review_issues_summary = {row["resolution"]: row["cnt"] for row in review_rows}

        criteria_rows = db.execute(
            "SELECT status, COUNT(*) as cnt FROM acceptance_criteria WHERE workspace_id = ? GROUP BY status",
            (ws["id"],)
        ).fetchall()
        criteria_summary = {row["status"]: row["cnt"] for row in criteria_rows}

        session_count = db.execute(
            "SELECT COUNT(*) as cnt FROM session_history WHERE workspace_id = ?",
            (ws["id"],)
        ).fetchone()["cnt"]

        discussion_rows = db.execute(
            "SELECT id, parent_id, text, author, status, created_at "
            "FROM discussions WHERE workspace_id = ? AND scope IS NULL AND parent_id IS NULL AND status = 'open' ORDER BY id",
            (ws["id"],)
        ).fetchall()
        discussions = []
        for row in discussion_rows:
            d = dict(row)
            replies = db.execute(
                "SELECT id, text, author, created_at FROM discussions WHERE parent_id = ? ORDER BY id",
                (row["id"],)
            ).fetchall()
            d["replies"] = [dict(r) for r in replies]
            discussions.append(d)
    finally:
        db.close()

    return {
        "phase": ws["phase"],
        "status": ws["status"],
        "scope": scope,
        "scope_status": ws["scope_status"],
        "phase_sequence": phase_sequence,
        "context": context,
        "discussions": discussions,
        "plan_summary": plan_summary,
        "progress_summary": progress_summary,
        "research_summary": research_summary,
        "unresolved_comments_count": comment_count,
        "review_issues_summary": review_issues_summary,
        "criteria_summary": criteria_summary,
        "previous_sessions_count": session_count,
        "locale": ws["locale"],
        "branch": ws["branch"],
        "working_dir": ws["working_dir"],
        "_detail_tools": {
            "plan": t("mcp.tool.getState.detail.plan", locale),
            "progress": t("mcp.tool.getState.detail.progress", locale),
            "research": t("mcp.tool.getState.detail.research", locale),
            "comments": t("mcp.tool.getState.detail.comments", locale),
            "review_issues": t("mcp.tool.getState.detail.reviewIssues", locale),
            "criteria": t("mcp.tool.getState.detail.criteria", locale),
        },
    }


@mcp.tool()
def workspace_advance(commit_hash: str = "", no_further_research_needed: bool = False) -> dict:
    """Request phase advancement. Provide commit_hash when at commit phases (3.N.4).

    At phase 1.1 (research → proving), you MUST set no_further_research_needed=True to confirm
    you have gathered all necessary information. If you're unsure, review your research findings
    against the research discussions — post new discussions and run more research if gaps exist.

    User gates (2.1, 3.N.3, 4.2) require human approval via admin panel — advance returns 409.
    When the user REJECTS at a gate, phase reverts to the previous step (e.g. 3.N.3 → 3.N.2).
    Read user comments via workspace_get_comments, fix the issues, then call workspace_advance
    to return to the gate for re-review. Do NOT ask the user to approve in order to fix — fix first, then re-submit."""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    from advance_service import perform_advance
    body = {}
    if commit_hash:
        body["commit_hash"] = commit_hash
    if no_further_research_needed:
        body["no_further_research_needed"] = True
    result, code = perform_advance(ws, project["path"], body)
    return result


@mcp.tool()
def workspace_set_scope(scope: dict) -> dict:
    """Set workspace scope as a phase-keyed map. Allowed from phase 1 onwards.

    Setting scope automatically revokes approval — the user must review and re-approve
    the new scope in the admin panel before code edits are allowed.

    Format: {"3.1": {"must": ["src/models/"], "may": ["src/config/"]}, "3.2": {"must": [...], "may": [...]}}
    Each key is a sub-phase ID from the execution plan. 'must' directories MUST have changes for the phase to advance.
    'may' directories are permitted but not required."""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    phase = ws["phase"]
    scope_json = json.dumps(scope)

    db = get_db()
    try:
        if Phase(phase) < "1.0":
            return {"error": t("mcp.error.scopePhase0", locale)}

        db.execute("UPDATE workspaces SET scope_json = ? WHERE id = ?", (scope_json, ws["id"]))

        # Auto-revoke scope approval — user must re-approve the new scope
        db.execute("UPDATE workspaces SET scope_status = 'pending' WHERE id = ?", (ws["id"],))

        db.commit()
        return {"ok": True, "phase": phase, "scope_status": "pending", "note": t("mcp.error.scopeNoteRevoked", locale)}
    finally:
        db.close()


@mcp.tool()
def workspace_set_plan(plan: dict) -> dict:
    """Set the execution plan. Editable during and after planning (phase >= 2.0).

    The plan can be updated freely during planning. Once the user approves the plan
    in the admin panel, approval is revoked each time the plan is updated — the user
    must review and re-approve before the workflow can advance past planning.

    The previous plan is saved automatically — call workspace_restore_plan to revert
    if the new plan hasn't been approved yet.

    Expected format:
    {
        "description": "High-level plain text description of what this plan achieves",
        "systemDiagram": "mermaid diagram string or array of {title, diagram}",
        "execution": [
            {
                "id": "3.1",
                "name": "Sub-phase name",
                "tasks": [{"title": "...", "files": ["..."], "agent": "...", "status": "pending", "group": "optional group name"}]
            }
        ]
    }

    Tasks with the same "group" name run in parallel (fork/join in the diagram).
    Tasks without a group or with unique groups run sequentially.
    Groups execute in order of first appearance within the sub-phase.

    systemDiagram must be an array of {title: str, diagram: str} objects:
    - At minimum: one class/entity diagram + one sequence diagram
    - Multiple sequence diagrams are encouraged for multi-flow features
    - Example: [{"title": "Class Diagram", "diagram": "classDiagram\n..."}, {"title": "Auth Flow", "diagram": "sequenceDiagram\n..."}]

    Scope is separate from the plan — use workspace_set_scope to define the phase-keyed scope map."""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    phase = ws["phase"]
    if Phase(phase) < "2.0":
        return {"error": t("mcp.error.planPhase", locale)}

    plan_json = json.dumps(plan)
    db = get_db()
    try:
        # Save current plan as previous before overwriting
        db.execute(
            """UPDATE workspaces SET
                prev_plan_json = plan_json,
                prev_scope_json = scope_json,
                prev_phase = phase,
                prev_plan_status = plan_status,
                prev_scope_status = scope_status
            WHERE id = ?""",
            (ws["id"],)
        )

        db.execute("UPDATE workspaces SET plan_json = ? WHERE id = ?", (plan_json, ws["id"]))
        db.execute("UPDATE workspaces SET plan_status = 'pending', scope_status = 'pending' WHERE id = ?", (ws["id"],))

        # Adjust phase if in execution and new plan has fewer sub-phases
        current_phase = ws["phase"]
        match = re.match(r'^3\.(\d+)\.\d+$', current_phase)
        if match:
            execution = plan.get("execution", [])
            if not execution:
                new_phase = "2.0"
            elif int(match.group(1)) > len(execution):
                new_phase = "3.0"
            else:
                new_phase = current_phase
            if new_phase != current_phase:
                db.execute("UPDATE workspaces SET phase = ? WHERE id = ?", (new_phase, ws["id"]))

        db.commit()
        return {"ok": True, "plan_status": "pending", "scope_status": "pending", "note": t("mcp.error.planNoteRevoked", locale)}
    finally:
        db.close()


@mcp.tool()
def workspace_get_plan() -> dict:
    """Get the full execution plan including system diagram and all sub-phases with tasks.

    Returns the complete plan JSON: description, systemDiagram, and execution array with
    tasks per sub-phase. Use workspace_get_state to see the current scope map."""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    plan = json.loads(ws["plan_json"]) if ws["plan_json"] else {"description": "", "systemDiagram": "", "execution": []}
    return plan


@mcp.tool()
def workspace_restore_plan() -> dict:
    """Restore the previous plan version, swapping it with the current plan.

    Only works if current plan is NOT approved. If you need to revert an incorrectly
    set plan, call this before the user approves it.

    The previous plan's phase position is also restored — you'll return to wherever
    you were when that plan was active.
    """
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"

    if not ws["prev_plan_json"]:
        return {"error": t("mcp.error.noPreviousPlan", locale)}

    if ws["plan_status"] == "approved":
        return {"error": t("mcp.error.planApproved", locale)}

    db = get_db()
    try:
        # Swap current and prev (SQLite evaluates all RHS from original row before updating)
        db.execute("""
            UPDATE workspaces SET
                plan_json = prev_plan_json,
                scope_json = prev_scope_json,
                phase = prev_phase,
                plan_status = prev_plan_status,
                scope_status = prev_scope_status,
                prev_plan_json = plan_json,
                prev_scope_json = scope_json,
                prev_phase = phase,
                prev_plan_status = plan_status,
                prev_scope_status = scope_status
            WHERE id = ?
        """, (ws["id"],))
        db.commit()

        ws2 = db.execute("SELECT phase, plan_status FROM workspaces WHERE id = ?", (ws["id"],)).fetchone()
        return {
            "restored": True,
            "phase": ws2["phase"],
            "plan_status": ws2["plan_status"],
            "message": t("mcp.restorePlan.message", locale, phase=ws2["phase"]),
        }
    finally:
        db.close()


@mcp.tool()
def workspace_post_discussion(topic: str, parent_id: int = 0, type: str = "general") -> dict:
    """Raise an open discussion point — architectural decisions, research questions, TBDs.

    These are NOT chat messages. They are important topics that need research, discussion,
    or decision from either the agent or the human. Examples:
    - 'Should we use event-driven logging or centralized logger?'
    - 'Hibernate Envers vs custom audit implementation'
    - 'Async vs sync approach for trade operation logging'

    Discussions are visible in the admin panel where either side can add context and resolve them.
    Use parent_id to reply to an existing discussion (0 = new root discussion).
    type: 'general' (default) or 'research'. Research discussions represent questions
    that need investigation — they are tracked and must have linked research findings
    before the workflow can advance past the research phase."""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    db = get_db()
    try:
        resolved_parent_id = parent_id if parent_id else None

        if resolved_parent_id:
            parent = db.execute(
                "SELECT id FROM discussions WHERE id = ? AND workspace_id = ?",
                (resolved_parent_id, ws["id"])
            ).fetchone()
            if not parent:
                return {"error": t("mcp.error.parentDiscussionNotFound", locale, id=resolved_parent_id)}

        cursor = db.execute(
            "INSERT INTO discussions (workspace_id, parent_id, text, author, type, status, created_at) "
            "VALUES (?, ?, ?, 'agent', ?, 'open', ?)",
            (ws["id"], resolved_parent_id, topic, type, datetime.now().isoformat())
        )
        db.commit()
        return {"ok": True, "discussion_id": cursor.lastrowid}
    finally:
        db.close()


@mcp.tool()
def workspace_save_research(topic: str, findings: list, discussion_id: int = 0) -> dict:
    """Save research findings. Called by researcher sub-agents after investigation.

    discussion_id: Optional — ID of the research discussion this answers. Link your research
    to the discussion that raised the question. Required for advancing past research phase
    (all unresolved research discussions must have linked findings).

    Each finding must include a typed proof — a verifiable reference to actual evidence:
    {
        "summary": "What was found",
        "details": "Detailed explanation",
        "proof": { ... type-specific fields ... }
    }

    PROOF TYPES:

    type: "code" — Code reference (code-researcher, senior-code-researcher)
    {
        "type": "code",
        "file": "path/to/file.java",
        "line_start": 10,
        "line_end": 30,
        "snippet_start": 15,
        "snippet_end": 25
    }
    - file: path relative to workspace root
    - line_start/line_end: PRECISE proof range — only the lines necessary to prove your point.
      Try to stay under 20-30 lines, but no hard limit if genuinely needed.
    - snippet_start/snippet_end: a 15-line (max) window WITHIN the proof range for the
      quick-reference quote. The server reads the actual file to render this — do NOT
      send snippet text. Pick the most relevant lines from the proof range.

    type: "web" — Web source (web-researcher)
    {
        "type": "web",
        "url": "https://docs.example.com/...",
        "title": "Page Title",
        "quote": "Actual text from the source"
    }
    - url: source URL (required)
    - title: page/article title
    - quote: verbatim text from the source. Required because server cannot fetch web pages.

    type: "diff" — Git commit/diff reference (diff-researcher)
    {
        "type": "diff",
        "commit": "abc123f",
        "file": "path/to/file.java",
        "description": "What this commit shows and why it proves the finding"
    }
    - commit: commit hash (required)
    - file: specific file in the commit (optional — omit for whole-commit findings)
    - description: mandatory context explaining what the diff proves

    Returns the research entry ID for reference."""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    if not findings:
        return {"error": t("mcp.error.noFindings", locale)}

    # Enrich code proofs: read actual file to populate snippet text
    working_dir = ws["working_dir"]

    # Normalize proof file paths: resolve relative paths against cwd, then make relative to working_dir
    cwd = os.getcwd()
    for finding in findings:
        proof = finding.get("proof", {})
        file_ref = proof.get("file")
        if not file_ref:
            continue
        # Resolve against cwd to get absolute path
        abs_path = Path(cwd) / file_ref if not Path(file_ref).is_absolute() else Path(file_ref)
        abs_path = abs_path.resolve()
        # Make relative to working_dir if possible
        try:
            proof["file"] = str(abs_path.relative_to(Path(working_dir).resolve()))
        except ValueError:
            # File is outside the workspace — store absolute path
            proof["file"] = str(abs_path)

    for finding in findings:
        proof = finding.get("proof", {})
        if proof.get("type") == "code" and proof.get("snippet_start") and proof.get("snippet_end"):
            file_path = Path(working_dir) / proof["file"]
            if file_path.exists():
                try:
                    lines = file_path.read_text().splitlines()
                    start = max(0, proof["snippet_start"] - 1)
                    end = min(len(lines), proof["snippet_end"])
                    proof["snippet"] = "\n".join(lines[start:end])
                except Exception:
                    pass

    db = get_db()
    try:
        resolved_discussion_id = discussion_id if discussion_id else None
        cursor = db.execute(
            "INSERT INTO research_entries (workspace_id, topic, findings_json, discussion_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (ws["id"], topic, json.dumps(findings), resolved_discussion_id, datetime.now().isoformat())
        )
        db.commit()
        return {"ok": True, "research_id": cursor.lastrowid}
    finally:
        db.close()


@mcp.tool()
def workspace_list_research() -> list:
    """List all research entries for the current workspace. Returns id, topic, findings count, and proven status.

    Does NOT return full findings content — use workspace_get_research to retrieve specific entries."""
    ws, project = _detect_workspace()
    if not ws:
        return [{"error": t("mcp.error.noWorkspace")}]

    db = get_db()
    try:
        rows = db.execute(
            "SELECT id, topic, findings_json, proven, created_at "
            "FROM research_entries WHERE workspace_id = ? ORDER BY id",
            (ws["id"],)
        ).fetchall()
        return [
            {
                "id": row["id"],
                "topic": row["topic"],
                "findings_count": len(json.loads(row["findings_json"])),
                "proven": row["proven"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    finally:
        db.close()


@mcp.tool()
def workspace_get_research(ids: list) -> list:
    """Get full research entries by IDs. Use for detailed review or proving.

    Returns complete findings with proofs for each requested ID."""
    ws, project = _detect_workspace()
    if not ws:
        return [{"error": t("mcp.error.noWorkspace")}]

    if not ids:
        return []

    db = get_db()
    try:
        placeholders = ",".join("?" * len(ids))
        rows = db.execute(
            f"SELECT id, topic, findings_json, proven, proven_notes, created_at "
            f"FROM research_entries WHERE workspace_id = ? AND id IN ({placeholders}) ORDER BY id",
            [ws["id"]] + list(ids)
        ).fetchall()
        return [
            {
                "id": row["id"],
                "topic": row["topic"],
                "findings": json.loads(row["findings_json"]),
                "proven": row["proven"],
                "proven_notes": row["proven_notes"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    finally:
        db.close()


@mcp.tool()
def workspace_prove_research(id: int, proven: bool, notes: str = "") -> dict:
    """Mark a research entry as proven or rejected. Called by prover agent after verification.

    - id: research entry ID
    - proven: True if findings verified, False if rejected
    - notes: optional explanation of verification result"""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    db = get_db()
    try:
        row = db.execute(
            "SELECT id FROM research_entries WHERE id = ? AND workspace_id = ?",
            (id, ws["id"])
        ).fetchone()
        if not row:
            return {"error": t("mcp.error.researchEntryNotFound", locale, id=id)}

        db.execute(
            "UPDATE research_entries SET proven = ?, proven_notes = ? WHERE id = ?",
            (1 if proven else -1, notes or None, id)
        )
        db.commit()
        return {"ok": True, "id": id, "proven": proven}
    finally:
        db.close()


@mcp.tool()
def workspace_get_comments(scope: str = "", unresolved_only: bool = True) -> list:
    """Get review comments, optionally filtered by scope. Returns list of comment objects (empty list if none)."""
    ws, project = _detect_workspace()
    if not ws:
        return [{"error": t("mcp.error.noWorkspace")}]

    db = get_db()
    try:
        if scope:
            query = (
                "SELECT id, parent_id, scope, target, file_path, line_start, line_end, line_hash, "
                "text, author, created_at, status, resolved_at, resolution "
                "FROM discussions WHERE workspace_id = ? AND scope IS NOT NULL AND parent_id IS NULL AND scope = ?"
            )
            params = [ws["id"], scope]
        else:
            query = (
                "SELECT id, parent_id, scope, target, file_path, line_start, line_end, line_hash, "
                "text, author, created_at, status, resolved_at, resolution "
                "FROM discussions WHERE workspace_id = ? AND scope IS NOT NULL AND parent_id IS NULL"
            )
            params = [ws["id"]]

        if unresolved_only:
            query += " AND status = 'open'"
        query += " ORDER BY id"

        rows = db.execute(query, params).fetchall()
        comments = []
        for row in rows:
            comment = {
                "id": row["id"],
                "scope": row["scope"],
                "target": row["target"],
                "file_path": row["file_path"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "text": row["text"],
                "author": row["author"],
                "created_at": row["created_at"],
                "resolved": row["status"] == "resolved",
                "resolution": row["resolution"],
            }
            replies = db.execute(
                "SELECT id, text, author, created_at, status, resolved_at "
                "FROM discussions WHERE parent_id = ? ORDER BY id",
                (row["id"],)
            ).fetchall()
            comment["replies"] = [dict(r) for r in replies]
            comments.append(comment)
        return comments
    finally:
        db.close()


@mcp.tool()
def workspace_post_comment(
    file_path: str,
    line_start: int,
    line_end: int,
    text: str,
    parent_id: int = 0,
) -> dict:
    """Post a review comment on specific file lines. Used by code-reviewer agents during review phases.

    - file_path: path relative to workspace root
    - line_start/line_end: line range being commented on
    - text: the review comment
    - parent_id: reply to existing comment (0 = new root comment)"""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"

    if not file_path or not file_path.strip():
        return {"error": t("mcp.error.filePathRequired", locale)}
    if not text or not text.strip():
        return {"error": t("mcp.error.textRequired", locale)}

    db = get_db()
    try:
        resolved_parent_id = None
        if parent_id > 0:
            parent = db.execute(
                "SELECT id FROM discussions WHERE id = ? AND workspace_id = ?",
                (parent_id, ws["id"])
            ).fetchone()
            if not parent:
                return {"error": t("mcp.error.parentCommentNotFound", locale, id=parent_id)}
            resolved_parent_id = parent_id

        cursor = db.execute(
            "INSERT INTO discussions "
            "(workspace_id, parent_id, scope, target, file_path, line_start, line_end, "
            "text, author, status, resolution, created_at) "
            "VALUES (?, ?, 'review', ?, ?, ?, ?, ?, 'agent', 'open', 'open', ?)",
            (ws["id"], resolved_parent_id, file_path.strip(), file_path.strip(),
             line_start, line_end, text.strip(), datetime.now().isoformat())
        )
        db.commit()
        return {"ok": True, "id": cursor.lastrowid}
    finally:
        db.close()


@mcp.tool()
def workspace_resolve_comment(comment_id: int) -> dict:
    """Mark a review comment as resolved. Call after addressing feedback from code review.

    - comment_id: the ID of the comment (from workspace_get_comments or workspace_get_state)
    - Only resolves comments belonging to the current workspace (security check)
    - Cannot resolve scope='review' items — use workspace_resolve_review_issue instead"""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    db = get_db()
    try:
        comment = db.execute(
            "SELECT id, scope FROM discussions WHERE id = ? AND workspace_id = ? AND scope IS NOT NULL",
            (comment_id, ws["id"])
        ).fetchone()
        if not comment:
            return {"error": t("mcp.error.commentNotFound", locale, comment_id=comment_id)}

        if comment["scope"] == "review":
            return {"error": t("mcp.error.reviewScopeResolveBlocked", locale)}

        db.execute(
            "UPDATE discussions SET status = 'resolved', resolved_at = ? WHERE id = ?",
            (datetime.now().isoformat(), comment_id)
        )
        db.commit()
        return {"ok": True, "comment_id": comment_id, "resolved": True}
    finally:
        db.close()


@mcp.tool()
def workspace_submit_review_issue(file_path: str, line_start: int, line_end: int, severity: str, description: str) -> dict:
    """Submit a code review finding. Only critical and major issues are saved — minor/style issues are dropped.

    - file_path: path relative to workspace root
    - line_start: first line of the problematic code
    - line_end: last line of the problematic code
    - severity: 'critical' or 'major' (others rejected)
    - description: what the issue is and why it matters"""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    if severity not in ("critical", "major"):
        return {"error": t("mcp.error.invalidSeverity", locale)}

    working_dir = ws["working_dir"]
    full_path = Path(working_dir) / file_path
    if not full_path.exists():
        return {"error": t("mcp.error.fileNotFound", locale, file_path=file_path)}

    try:
        lines = full_path.read_text().splitlines()
        start = max(0, line_start - 1)
        if start >= len(lines):
            return {"error": t("mcp.error.lineStartBeyondFile", locale, line_start=line_start, length=len(lines))}
    except Exception as e:
        return {"error": t("mcp.error.failedToReadFile", locale, error=str(e))}

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO discussions "
            "(workspace_id, scope, target, file_path, line_start, line_end, "
            "text, author, status, resolution, created_at) "
            "VALUES (?, 'review', ?, ?, ?, ?, ?, 'reviewer', 'open', 'open', ?)",
            (ws["id"], file_path.strip(), file_path.strip(),
             line_start, line_end, description.strip(), datetime.now().isoformat())
        )
        db.commit()
        return {"ok": True, "id": cursor.lastrowid}
    finally:
        db.close()


@mcp.tool()
def workspace_get_review_issues(status: str = "") -> list:
    """Get all review items for the current workspace.

    - status: filter by resolution ('open', 'fixed', 'false_positive', 'out_of_scope'). Empty = all.
    Returns list of review items with id, file_path, lines, description, resolution, author, resolved."""
    ws, project = _detect_workspace()
    if not ws:
        return [{"error": t("mcp.error.noWorkspace")}]

    db = get_db()
    try:
        query = (
            "SELECT id, file_path, line_start, line_end, text, resolution, author, status, created_at "
            "FROM discussions WHERE workspace_id = ? AND scope = 'review' AND parent_id IS NULL"
        )
        params = [ws["id"]]
        if status:
            query += " AND resolution = ?"
            params.append(status)
        query += " ORDER BY id"

        rows = db.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "file_path": row["file_path"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "description": row["text"],
                "resolution": row["resolution"],
                "author": row["author"],
                "resolved": row["status"] == "resolved",
            }
            for row in rows
        ]
    finally:
        db.close()


@mcp.tool()
def workspace_resolve_review_issue(issue_id: int, resolution: str) -> dict:
    """Set the resolution on a review item. Called by agents after addressing feedback.

    - issue_id: the review item ID (from workspace_get_review_issues or workspace_get_comments)
    - resolution:
      - 'fixed': code was changed to address the issue
      - 'false_positive': issue is invalid, code is correct as-is
      - 'out_of_scope': legitimate issue but outside the allowed scope"""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    if resolution not in ("fixed", "false_positive", "out_of_scope"):
        return {"error": t("mcp.error.invalidResolution", locale)}

    db = get_db()
    try:
        row = db.execute(
            "SELECT id FROM discussions WHERE id = ? AND workspace_id = ? AND scope = 'review'",
            (issue_id, ws["id"])
        ).fetchone()
        if not row:
            return {"error": t("mcp.error.reviewIssueNotFound", locale, issue_id=issue_id)}

        db.execute(
            "UPDATE discussions SET resolution = ? WHERE id = ?",
            (resolution, issue_id)
        )
        db.commit()
        return {"ok": True, "issue_id": issue_id, "resolution": resolution}
    finally:
        db.close()


@mcp.tool()
def workspace_update_progress(phase: str, summary: str, details: dict = None) -> dict:
    """Update progress for a phase. Called by orchestrator after completing phase work.

    - phase: the phase key (e.g. "1.0", "1", "2", "3.1", "4")
    - summary: concise summary of what was done (1-3 sentences)
    - details: rich structured record of the phase work. Include as much context as needed:
      {
        "actions": ["what was done, step by step"],
        "obstacles": ["problems hit and how they were resolved"],
        "decisions": ["key choices made and rationale"],
        "findings": ["important discoveries or results"],
        "files_changed": ["list of files modified"],
        "agents_deployed": ["which agents were used and for what"],
        "outcome": "final result of this phase"
      }
      All fields in details are optional — include whatever is relevant.

    The progress entry is used for:
    1. Phase gate validation (summary must be non-empty to advance)
    2. Session recovery after compaction (details reconstructs what happened)
    3. Daily reflection queries (entries are date-stamped)

    Calling with the same phase key updates the existing entry (updated_at is refreshed).
    """
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    now = datetime.now().isoformat()
    details_json = json.dumps(details) if details else None

    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM progress_entries WHERE workspace_id = ? AND phase = ?",
            (ws["id"], phase)
        ).fetchone()

        if existing:
            db.execute(
                "UPDATE progress_entries SET summary = ?, details_json = ?, updated_at = ? WHERE id = ?",
                (summary, details_json, now, existing["id"])
            )
        else:
            db.execute(
                "INSERT INTO progress_entries (workspace_id, phase, summary, details_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ws["id"], phase, summary, details_json, now, now)
            )
        db.commit()
        return {"ok": True, "phase": phase}
    finally:
        db.close()


@mcp.tool()
def workspace_get_progress(phase: str = "") -> dict:
    """Get progress entries with full details. Optionally filter by phase key.

    - phase: specific phase key (e.g. "1.0", "2.0"). Empty = all phases.

    Returns dict of phase → {summary, details, created_at, updated_at}."""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    db = get_db()
    try:
        if phase:
            rows = db.execute(
                "SELECT phase, summary, details_json, created_at, updated_at "
                "FROM progress_entries WHERE workspace_id = ? AND phase = ?",
                (ws["id"], phase)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT phase, summary, details_json, created_at, updated_at "
                "FROM progress_entries WHERE workspace_id = ? ORDER BY id",
                (ws["id"],)
            ).fetchall()

        progress = {}
        for row in rows:
            entry = {"summary": row["summary"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
            if row["details_json"]:
                try:
                    entry["details"] = json.loads(row["details_json"])
                except json.JSONDecodeError:
                    pass
            progress[row["phase"]] = entry
        return progress
    finally:
        db.close()


@mcp.tool()
def workspace_propose_criteria(type: str, description: str, details_json: str = "") -> dict:
    """Propose an acceptance criterion for the workspace. Called by the agent to suggest verifiable criteria.

    - type: one of 'unit_test', 'integration_test', 'bdd_scenario', 'custom'
    - description: human-readable description of what must pass
    - details_json: optional JSON string with type-specific details (test names, file paths, scenario steps)

    Proposed criteria are visible in the admin panel where the user can accept or reject them."""
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    if type not in VALID_CRITERIA_TYPES:
        return {"error": t("mcp.error.invalidCriteriaType", locale, type=type, valid_types=", ".join(VALID_CRITERIA_TYPES))}

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO acceptance_criteria "
            "(workspace_id, type, description, details_json, source, status, created_at) "
            "VALUES (?, ?, ?, ?, 'agent', 'proposed', ?)",
            (ws["id"], type, description, details_json or None, datetime.now().isoformat())
        )
        db.commit()
        criterion_id = cursor.lastrowid
        row = db.execute(
            "SELECT id, type, description, details_json, source, status, validated, validation_message "
            "FROM acceptance_criteria WHERE id = ?",
            (criterion_id,)
        ).fetchone()
        return {
            "ok": True,
            "criterion": {
                "id": row["id"],
                "type": row["type"],
                "description": row["description"],
                "details": json.loads(row["details_json"]) if row["details_json"] else None,
                "source": row["source"],
                "status": row["status"],
                "validated": row["validated"],
                "validation_message": row["validation_message"],
            }
        }
    finally:
        db.close()


@mcp.tool()
def workspace_get_criteria(status: str = "", type: str = "") -> list:
    """Get acceptance criteria for the current workspace, optionally filtered.

    - status: filter by status ('proposed', 'accepted', 'rejected'). Empty = all.
    - type: filter by type ('unit_test', 'integration_test', 'bdd_scenario', 'custom'). Empty = all.

    Returns list of criteria with id, type, description, details, source, status, validated, validation_message."""
    ws, project = _detect_workspace()
    if not ws:
        return [{"error": t("mcp.error.noWorkspace")}]

    db = get_db()
    try:
        query = (
            "SELECT id, type, description, details_json, source, status, validated, validation_message "
            "FROM acceptance_criteria WHERE workspace_id = ?"
        )
        params = [ws["id"]]
        if status:
            query += " AND status = ?"
            params.append(status)
        if type:
            query += " AND type = ?"
            params.append(type)
        query += " ORDER BY id"

        rows = db.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "type": row["type"],
                "description": row["description"],
                "details": json.loads(row["details_json"]) if row["details_json"] else None,
                "source": row["source"],
                "status": row["status"],
                "validated": row["validated"],
                "validation_message": row["validation_message"],
            }
            for row in rows
        ]
    finally:
        db.close()


@mcp.tool()
def workspace_update_criteria(criterion_id: int, description: str = "", details_json: str = "") -> dict:
    """Update an existing acceptance criterion's description and/or details. Use this to fill in
    file paths, test names, and refined descriptions for criteria created by the user.

    - criterion_id: ID of the criterion to update
    - description: updated description (optional, keeps existing if empty)
    - details_json: updated details JSON (optional, keeps existing if empty)
      For unit_test/integration_test: {"file": "path/to/TestFile.java", "test_names": ["testMethod1", "testMethod2"]}
      For bdd_scenario: {"file": "features/file.feature", "scenario_names": ["scenario1"]}
      For custom: {"instruction": "description of what to verify"}
    """
    ws, project = _detect_workspace()
    if not ws:
        return {"error": t("mcp.error.noWorkspace")}

    locale = ws["locale"] or "en"
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM acceptance_criteria WHERE id = ? AND workspace_id = ?",
            (criterion_id, ws["id"])
        ).fetchone()
        if not row:
            return {"error": t("mcp.error.criterionNotFound", locale, criterion_id=criterion_id)}

        if row["status"] == "accepted":
            return {"error": t("mcp.error.cannotUpdateAcceptedCriteria", locale)}

        reset_status = row["status"] == "rejected"

        updates = []
        params = []
        if description:
            updates.append("description = ?")
            params.append(description)
        if details_json:
            updates.append("details_json = ?")
            params.append(details_json)

        if not updates:
            return {"error": t("mcp.error.nothingToUpdate", locale)}

        params.append(criterion_id)
        db.execute(
            f"UPDATE acceptance_criteria SET {', '.join(updates)} WHERE id = ?",
            params
        )

        if reset_status:
            db.execute("UPDATE acceptance_criteria SET status = 'proposed' WHERE id = ?", (criterion_id,))

        db.commit()

        updated = db.execute(
            "SELECT * FROM acceptance_criteria WHERE id = ?", (criterion_id,)
        ).fetchone()
        result = {"ok": True, "id": criterion_id}
        if reset_status:
            result["status_reset"] = "proposed"
        result["criterion"] = {
            "id": updated["id"],
            "type": updated["type"],
            "description": updated["description"],
            "details": json.loads(updated["details_json"]) if updated["details_json"] else None,
            "status": updated["status"],
        }
        return result
    finally:
        db.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
