from mcp_tools import mcp
from core.db import get_db
from services import improvement_service


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
