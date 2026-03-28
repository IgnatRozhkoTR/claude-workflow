import json

from mcp_tools import mcp, with_mcp_workspace
from core.helpers import compute_phase_sequence
from core.i18n import t
from services import discussion_service
from services import plan_service
from services import progress_service
from services import research_service


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
