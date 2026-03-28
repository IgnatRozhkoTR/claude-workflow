import json

from mcp_tools import mcp, with_mcp_workspace
from services import progress_service


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
