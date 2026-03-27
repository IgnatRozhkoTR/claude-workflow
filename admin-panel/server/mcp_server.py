"""MCP server for workspace state management (stdio transport)."""
import functools
import inspect
import json
import logging
import os
import re
import sys

logger = logging.getLogger(__name__)
from datetime import datetime
from pathlib import Path

# Add server/ to path for shared imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP
from db import get_db, init_db
from helpers import VALID_CRITERIA_TYPES, compute_phase_sequence
from i18n import t
from phase import Phase
import comment_service
import criteria_service
import discussion_service
import improvement_service
import plan_service
import progress_service
import research_service
import scope_service
import verification_service

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


_INJECTED_PARAMS = ("ws", "project", "db", "locale")


def with_mcp_workspace(fn):
    """Decorator that injects workspace context into MCP tool functions.

    Calls _detect_workspace(), opens a DB connection, and passes (ws, project, db, locale)
    as the first positional arguments to the wrapped function.
    Returns an error dict/list if no workspace is detected.
    Closes the DB connection in a finally block. Does NOT auto-commit.
    """
    sig = inspect.signature(fn)
    exposed_params = [p for name, p in sig.parameters.items() if name not in _INJECTED_PARAMS]
    exposed_sig = sig.replace(parameters=exposed_params)

    returns_list = sig.return_annotation is list

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        ws, project = _detect_workspace()
        if not ws:
            error = {"error": t("mcp.error.noWorkspace")}
            return [error] if returns_list else error

        locale = ws["locale"] or "en"
        db = get_db()
        try:
            return fn(ws, project, db, locale, *args, **kwargs)
        finally:
            db.close()

    wrapper.__signature__ = exposed_sig
    return wrapper


@mcp.tool()
@with_mcp_workspace
def workspace_get_state(ws, project, db, locale) -> dict:
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
    scope = plan_service.get_scope(ws)
    plan = plan_service.get_plan(ws)
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

    progress_summary = progress_service.get_progress_map(db, ws["id"])

    research_entries = research_service.list_research(db, ws["id"])
    research_summary = [{"id": e["id"], "topic": e["topic"], "proven": e["proven"]} for e in research_entries]

    comment_count = db.execute(
        "SELECT COUNT(*) as cnt FROM discussions WHERE workspace_id = ? AND scope IS NOT NULL AND status = 'open'",
        (ws["id"],)
    ).fetchone()["cnt"]

    review_rows = db.execute(
        "SELECT resolution, COUNT(*) as cnt FROM discussions "
        "WHERE workspace_id = ? AND scope = 'review' AND parent_id IS NULL GROUP BY resolution",
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

    discussions = discussion_service.list_discussions(db, ws["id"], open_only=True)

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
@with_mcp_workspace
def workspace_advance(ws, project, db, locale, commit_hash: str = "", no_further_research_needed: bool = False) -> dict:
    """Request phase advancement. Provide commit_hash when at commit phases (3.N.4).

    At phase 1.1 (research → proving), you MUST set no_further_research_needed=True to confirm
    you have gathered all necessary information. If you're unsure, review your research findings
    against the research discussions — post new discussions and run more research if gaps exist.

    User gates (1.4, 2.1, 3.N.3, 4.2) require human approval via admin panel — advance returns 409.
    When the user REJECTS at a gate, phase reverts to the previous step (e.g. 3.N.3 → 3.N.2).
    Read user comments via workspace_get_comments, fix the issues, then call workspace_advance
    to return to the gate for re-review. Do NOT ask the user to approve in order to fix — fix first, then re-submit."""
    from advance_service import perform_advance
    body = {}
    if commit_hash:
        body["commit_hash"] = commit_hash
    if no_further_research_needed:
        body["no_further_research_needed"] = True
    result, code = perform_advance(ws, project["path"], body)
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_set_scope(ws, project, db, locale, scope: dict) -> dict:
    """Set workspace scope as a phase-keyed map. Allowed from phase 1 onwards.

    Setting scope automatically revokes approval — the user must review and re-approve
    the new scope in the admin panel before code edits are allowed.

    Format: {"3.1": {"must": ["src/models/"], "may": ["src/config/"]}, "3.2": {"must": [...], "may": [...]}}
    Each key is a sub-phase ID from the execution plan. 'must' directories MUST have changes for the phase to advance.
    'may' directories are permitted but not required."""
    result = scope_service.set_scope(db, ws, scope)
    if "error" not in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_set_plan(ws, project, db, locale, plan: dict) -> dict:
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
    result = plan_service.set_plan(db, ws, plan)
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_plan(ws, project, db, locale) -> dict:
    """Get the full execution plan including system diagram and all sub-phases with tasks.

    Returns the complete plan JSON: description, systemDiagram, and execution array with
    tasks per sub-phase. Use workspace_get_state to see the current scope map."""
    return plan_service.get_plan(ws)


@mcp.tool()
@with_mcp_workspace
def workspace_extend_plan(ws, project, db, locale, subphase: dict, scope: dict, diagrams: list = None, replace_diagrams: bool = False) -> dict:
    """Append a new sub-phase to the execution plan without rewriting existing sub-phases.

    - subphase: a single execution item with 'name' (string) and 'tasks' (list of task objects).
      The 'id' is auto-assigned as 3.(max_n+1). Each task needs: title (string), files (list), agent (string).
      Optional task fields: group (string), status (string, default 'pending').
    - scope: scope entry for the new sub-phase with must and may patterns, e.g. {"must": ["src/foo/"], "may": ["src/bar/"]}
    - diagrams: optional list of system diagrams to add, each with 'title' (string) and 'diagram' (string, Mermaid syntax).
      By default, diagrams are appended to the existing list. Set replace_diagrams=true to replace the entire list.
    - replace_diagrams: if true, replace all existing diagrams with the provided list. If false (default), append.

    The plan_status and scope_status are set to 'pending' (approval revoked).
    Existing sub-phases and their data are not modified."""
    result = plan_service.extend_plan(db, ws, subphase, scope, diagrams, replace_diagrams)
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_restore_plan(ws, project, db, locale) -> dict:
    """Restore the previous plan version, swapping it with the current plan.

    Only works if current plan is NOT approved. If you need to revert an incorrectly
    set plan, call this before the user approves it.

    The previous plan's phase position is also restored — you'll return to wherever
    you were when that plan was active.
    """
    if not ws["prev_plan_json"]:
        return {"error": t("mcp.error.noPreviousPlan", locale)}

    if ws["plan_status"] == "approved":
        return {"error": t("mcp.error.planApproved", locale)}

    new_ws = plan_service.restore_plan(db, ws)
    db.commit()

    return {
        "restored": True,
        "phase": new_ws["phase"],
        "plan_status": new_ws["plan_status"],
        "message": t("mcp.restorePlan.message", locale, phase=new_ws["phase"]),
    }


@mcp.tool()
@with_mcp_workspace
def workspace_post_discussion(ws, project, db, locale, topic: str, parent_id: int = 0, type: str = "general") -> dict:
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
    result = discussion_service.post_discussion(
        db, ws["id"], topic, author="agent",
        disc_type=type, parent_id=parent_id if parent_id else None,
    )
    if "error" in result:
        return {"error": t("mcp.error.parentDiscussionNotFound", locale, id=result.get("parent_id", ""))}
    db.commit()
    return {"ok": True, "discussion_id": result["id"]}


@mcp.tool()
@with_mcp_workspace
def workspace_save_research(ws, project, db, locale, topic: str, findings: list, discussion_id: int = 0, summary: str = "") -> dict:
    """Save research findings. Called by researcher sub-agents after investigation.

    summary: Optional 2-3 sentence human-readable overview of the overall research findings.
    If provided, it appears in research lists without requiring full findings to be loaded.

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
    result = research_service.save_research(
        db, ws, topic, findings,
        discussion_id=discussion_id if discussion_id else None,
        summary=summary,
    )
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_list_research(ws, project, db, locale) -> list:
    """List all research entries for the current workspace. Returns id, topic, findings count, and proven status.

    Does NOT return full findings content — use workspace_get_research to retrieve specific entries."""
    return research_service.list_research(db, ws["id"])


@mcp.tool()
@with_mcp_workspace
def workspace_get_research(ws, project, db, locale, ids: list) -> list:
    """Get full research entries by IDs. Use for detailed review or proving.

    Returns complete findings with proofs for each requested ID."""
    if not ids:
        return []

    return research_service.get_research(db, ws["id"], ids)


@mcp.tool()
@with_mcp_workspace
def workspace_prove_research(ws, project, db, locale, id: int, proven: bool, notes: str = "") -> dict:
    """Mark a research entry as proven or rejected. Called by prover agent after verification.

    - id: research entry ID
    - proven: True if findings verified, False if rejected
    - notes: optional explanation of verification result"""
    result = research_service.set_proven(db, id, ws["id"], proven, notes=notes)
    if "error" in result:
        return {"error": t("mcp.error.researchEntryNotFound", locale, id=id)}
    db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_comments(ws, project, db, locale, scope: str = "", unresolved_only: bool = True) -> list:
    """Get review comments, optionally filtered by scope. Returns list of comment objects (empty list if none)."""
    return comment_service.get_comments(
        db, ws["id"], scope=scope or None, unresolved_only=unresolved_only
    )


@mcp.tool()
@with_mcp_workspace
def workspace_post_comment(
    ws, project, db, locale,
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
    if not file_path or not file_path.strip():
        return {"error": t("mcp.error.filePathRequired", locale)}
    if not text or not text.strip():
        return {"error": t("mcp.error.textRequired", locale)}

    if parent_id > 0:
        parent = db.execute(
            "SELECT id FROM discussions WHERE id = ? AND workspace_id = ?",
            (parent_id, ws["id"])
        ).fetchone()
        if not parent:
            return {"error": t("mcp.error.parentCommentNotFound", locale, id=parent_id)}

    result = comment_service.post_comment(
        db, ws["id"], text=text.strip(), scope="review", author="agent",
        target=file_path.strip(), file_path=file_path.strip(),
        line_start=line_start, line_end=line_end,
        parent_id=parent_id if parent_id > 0 else None,
    )
    db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_resolve_comment(ws, project, db, locale, comment_id: int) -> dict:
    """Mark a review comment as resolved. Call after addressing feedback from code review.

    - comment_id: the ID of the comment (from workspace_get_comments or workspace_get_state)
    - Only resolves comments belonging to the current workspace (security check)
    - Cannot resolve scope='review' items — use workspace_resolve_review_issue instead"""
    result = comment_service.resolve_comment(db, comment_id, ws["id"], block_review_scope=True, locale=locale)
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_submit_review_issue(ws, project, db, locale, file_path: str, line_start: int, line_end: int, severity: str, description: str) -> dict:
    """Submit a code review finding. Only critical and major issues are saved — minor/style issues are dropped.

    - file_path: path relative to workspace root
    - line_start: first line of the problematic code
    - line_end: last line of the problematic code
    - severity: 'critical' or 'major' (others rejected)
    - description: what the issue is and why it matters"""
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

    result = comment_service.submit_review_issue(
        db, ws["id"], file_path, line_start, line_end, description, author="reviewer"
    )
    db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_review_issues(ws, project, db, locale, status: str = "") -> list:
    """Get all review items for the current workspace.

    - status: filter by resolution ('open', 'fixed', 'false_positive', 'out_of_scope'). Empty = all.
    Returns list of review items with id, file_path, lines, description, resolution, author, resolved."""
    return comment_service.get_review_issues(
        db, ws["id"], resolution=status or None
    )


@mcp.tool()
@with_mcp_workspace
def workspace_resolve_review_issue(ws, project, db, locale, issue_id: int, resolution: str) -> dict:
    """Set the resolution on a review item. Called by agents after addressing feedback.

    - issue_id: the review item ID (from workspace_get_review_issues or workspace_get_comments)
    - resolution:
      - 'fixed': code was changed to address the issue
      - 'false_positive': issue is invalid, code is correct as-is
      - 'out_of_scope': legitimate issue but outside the allowed scope
      - 'open': reset — used by review-validator to reopen incorrectly resolved issues"""
    if resolution not in ("fixed", "false_positive", "out_of_scope", "open"):
        return {"error": t("mcp.error.invalidResolution", locale)}

    result = comment_service.resolve_review_issue(
        db, issue_id, ws["id"], resolution, locale=locale
    )
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_set_impact_analysis(
    ws, project, db, locale,
    affected_flows: str = "",
    api_changes: str = "",
    data_flow_changes: str = "",
    external_dependencies: str = "",
    ticket_gaps: str = "",
    open_questions: str = "",
) -> dict:
    """Save structured impact analysis for the workspace. Called during phase 1.3.

    Each field is a text description of that aspect of the impact analysis:
    - affected_flows: Which user flows/interactions are affected
    - api_changes: API endpoint changes (new, modified, removed) and contract changes
    - data_flow_changes: Where key values come from, how data moves through the system
    - external_dependencies: DB migrations, infrastructure, coordination with other teams
    - ticket_gaps: What the ticket leaves ambiguous or underspecified
    - open_questions: Questions that need user input (can't be resolved from code/web)
    """
    analysis = {
        "affected_flows": affected_flows,
        "api_changes": api_changes,
        "data_flow_changes": data_flow_changes,
        "external_dependencies": external_dependencies,
        "ticket_gaps": ticket_gaps,
        "open_questions": open_questions,
    }

    progress_service.set_impact_analysis(db, ws["id"], analysis)
    db.commit()
    return {"ok": True}


@mcp.tool()
@with_mcp_workspace
def workspace_update_progress(ws, project, db, locale, phase: str, summary: str, details: dict = None) -> dict:
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
    details_json = json.dumps(details) if details else None

    result = progress_service.update_progress(db, ws["id"], phase, summary, details_json)
    db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_progress(ws, project, db, locale, phase: str = "") -> dict:
    """Get progress entries with full details. Optionally filter by phase key.

    - phase: specific phase key (e.g. "1.0", "2.0"). Empty = all phases.

    Returns dict of phase → {summary, details, created_at, updated_at}."""
    return progress_service.get_progress(db, ws["id"], phase_key=phase or None)


@mcp.tool()
@with_mcp_workspace
def workspace_propose_criteria(ws, project, db, locale, type: str, description: str, details_json: str = "") -> dict:
    """Propose an acceptance criterion for the workspace. Called by the agent to suggest verifiable criteria.

    - type: one of 'unit_test', 'integration_test', 'bdd_scenario', 'custom'
    - description: human-readable description of what must pass
    - details_json: optional JSON string with type-specific details
      For unit_test/integration_test: {"file": "path/to/TestFile.java", "test_names": ["testMethod1", "testMethod2"]}
      For bdd_scenario: {"file": "features/file.feature", "scenario_names": ["scenario1"]}
      For custom: {"instruction": "description of what to verify"}
      All types support an optional "verification_command" field — a shell command the server runs at commit time. Exit 0 = pass, non-zero = fail.

    Proposed criteria are visible in the admin panel where the user can accept or reject them."""
    if type not in VALID_CRITERIA_TYPES:
        return {"error": t("mcp.error.invalidCriteriaType", locale, type=type, valid_types=", ".join(VALID_CRITERIA_TYPES))}

    result = criteria_service.propose_criterion(
        db, ws["id"], type, description, details_json=details_json or None, source="agent"
    )
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_criteria(ws, project, db, locale, status: str = "", type: str = "") -> list:
    """Get acceptance criteria for the current workspace, optionally filtered.

    - status: filter by status ('proposed', 'accepted', 'rejected'). Empty = all.
    - type: filter by type ('unit_test', 'integration_test', 'bdd_scenario', 'custom'). Empty = all.

    Returns list of criteria with id, type, description, details, source, status, validated, validation_message."""
    return criteria_service.get_criteria(
        db, ws["id"], status=status or None, criterion_type=type or None
    )


@mcp.tool()
@with_mcp_workspace
def workspace_update_criteria(ws, project, db, locale, criterion_id: int, description: str = "", details_json: str = "") -> dict:
    """Update an existing acceptance criterion's description and/or details. Use this to fill in
    file paths, test names, and refined descriptions for criteria created by the user.

    - criterion_id: ID of the criterion to update
    - description: updated description (optional, keeps existing if empty)
    - details_json: updated details JSON (optional, keeps existing if empty)
      For unit_test/integration_test: {"file": "path/to/TestFile.java", "test_names": ["testMethod1", "testMethod2"]}
      For bdd_scenario: {"file": "features/file.feature", "scenario_names": ["scenario1"]}
      For custom: {"instruction": "description of what to verify"}
    """
    result = criteria_service.update_criterion(
        db, criterion_id, ws["id"],
        description=description or None, details_json=details_json or None
    )
    if "error" in result:
        error_key = result["error"]
        if error_key == "criterion_not_found":
            return {"error": t("mcp.error.criterionNotFound", locale, criterion_id=criterion_id)}
        if error_key == "cannot_update_accepted":
            return {"error": t("mcp.error.cannotUpdateAcceptedCriteria", locale)}
        if error_key == "nothing_to_update":
            return {"error": t("mcp.error.nothingToUpdate", locale)}
        return result
    db.commit()
    return result


@mcp.tool()
def workspace_report_improvement(scope: str, title: str, description: str, context: str = "") -> dict:
    """Report a potential improvement discovered during work. NOT workspace-bound — callable from anywhere.

    Use this when you discover something that could be done better in future workflows:
    - A correct way to run/build/test the application that was discovered through trial and error
    - A workflow pattern that didn't work well (e.g., teammate agent going idle)
    - A missing skill or documentation gap
    - A tool configuration that should be saved for reuse

    - scope: category of improvement — 'workflow', 'project', 'skill', 'tooling', 'documentation'
    - title: short summary (under 80 chars)
    - description: detailed description of what should be improved and how
    - context: optional — what happened that led to this discovery"""
    if scope not in ("workflow", "project", "skill", "tooling", "documentation"):
        return {"error": "Invalid scope. Must be one of: workflow, project, skill, tooling, documentation"}
    if not title or not title.strip():
        return {"error": "Title is required"}
    if not description or not description.strip():
        return {"error": "Description is required"}

    db = get_db()
    try:
        result = improvement_service.report_improvement(
            db, scope, title, description, context=context or None
        )
        db.commit()
        return result
    finally:
        db.close()


@mcp.tool()
def workspace_get_improvements(scope: str = "", status: str = "") -> list:
    """Get reported improvements, optionally filtered. NOT workspace-bound — callable from anywhere.

    - scope: filter by scope ('workflow', 'project', 'skill', 'tooling', 'documentation'). Empty = all.
    - status: filter by status ('open', 'resolved'). Empty = all.

    Returns list of improvements with id, scope, title, description, context, status, created_at."""
    db = get_db()
    try:
        return improvement_service.get_improvements(
            db, scope=scope or None, status=status or None
        )
    finally:
        db.close()


@mcp.tool()
@with_mcp_workspace
def workspace_get_verification_results(ws, project, db, locale, phase: str = "", run_id: int = 0) -> dict:
    """Get verification run results for the current workspace.

    - phase: filter by phase (e.g. "3.1.1"). Empty = latest run.
    - run_id: get specific run by ID. Takes precedence over phase.

    Returns run status and step-by-step results with output."""
    result = verification_service.get_verification_results(
        db, ws["id"], phase=phase or None, run_id=run_id if run_id else None
    )
    if not result:
        return {"message": "No verification runs found"}
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_get_verification_profiles(ws, project, db, locale) -> list:
    """Get all available verification profiles in the system.

    Returns profiles with their steps. Use workspace_assign_verification_profile to assign one to the current project."""
    return verification_service.get_all_profiles(db)


@mcp.tool()
@with_mcp_workspace
def workspace_create_verification_profile(ws, project, db, locale, name: str, language: str, description: str = "") -> dict:
    """Create a new verification profile. Use workspace_add_verification_step to add steps after creation.

    - name: display name (e.g. "Go", "Rust", "Java (Custom)")
    - language: language key (e.g. "go", "rust", "java")
    - description: what this profile checks"""
    if not name or not name.strip():
        return {"error": "Name is required"}
    if not language or not language.strip():
        return {"error": "Language is required"}
    result = verification_service.create_profile(db, name, language, description=description or None)
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_add_verification_step(ws, project, db, locale, profile_id: int, name: str, command: str,
                                     description: str = "", install_check_command: str = "",
                                     install_command: str = "", enabled: bool = True,
                                     sort_order: int = 0, timeout: int = 120,
                                     fail_severity: str = "blocking") -> dict:
    """Add a verification step to a profile.

    - profile_id: which profile to add the step to
    - name: step name (e.g. "Compilation", "Lint")
    - command: the shell command to run
    - install_check_command: optional — checks if tool is present
    - install_command: optional — installs tool if check fails
    - enabled: whether this step runs (default true)
    - sort_order: execution order (0 = first)
    - timeout: seconds, 0 = no timeout (default 120)
    - fail_severity: 'blocking' (stops advance) or 'warning' (logged only)"""
    if fail_severity not in ("blocking", "warning"):
        return {"error": "fail_severity must be 'blocking' or 'warning'"}
    result = verification_service.add_step(
        db, profile_id, name, command,
        description=description or None,
        install_check_command=install_check_command or None,
        install_command=install_command or None,
        enabled=enabled, sort_order=sort_order, timeout=timeout, fail_severity=fail_severity
    )
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_assign_verification_profile(ws, project, db, locale, profile_id: int, subpath: str = ".") -> dict:
    """Assign a verification profile to the current project (applies to all workspaces in the project).

    - profile_id: ID of the profile to assign (from workspace_get_verification_profiles)
    - subpath: subdirectory to run in (default "." = workspace root). Use for multi-language projects."""
    result = verification_service.assign_profile(db, ws["project_id"], profile_id, subpath=subpath)
    if "ok" in result:
        db.commit()
    return result


@mcp.tool()
@with_mcp_workspace
def workspace_submit_validation(ws, project, db, locale, phase: str, status: str, findings: list = None) -> dict:
    """Submit validation results from a validator agent. Replaces file-based validation/3.N.json.

    - phase: the current phase (e.g. "3.1.1")
    - status: 'clean' (no issues) or 'dirty' (issues found)
    - findings: optional list of finding descriptions (strings)"""
    if status not in ("clean", "dirty"):
        return {"error": "Status must be 'clean' or 'dirty'"}

    from datetime import datetime
    now = datetime.now().isoformat()
    run_cursor = db.execute(
        "INSERT INTO verification_runs (workspace_id, phase, status, started_at, completed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws["id"], phase, "passed" if status == "clean" else "failed", now, now)
    )
    run_id = run_cursor.lastrowid

    if findings:
        for finding in findings:
            db.execute(
                "INSERT INTO verification_step_results (run_id, step_name, profile_name, status, output, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, "Code Review", "Agent Validation", "failed" if status == "dirty" else "passed",
                 finding if isinstance(finding, str) else str(finding), 0)
            )

    db.commit()
    return {"ok": True, "run_id": run_id}


if __name__ == "__main__":
    mcp.run(transport="stdio")
