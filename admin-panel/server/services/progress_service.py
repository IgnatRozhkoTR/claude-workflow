"""Progress and impact analysis domain logic.

All progress/impact business logic lives here. MCP tools and route handlers
are thin wrappers that delegate to this module.
"""
import json
from datetime import datetime


def update_progress(db, workspace_id, phase_key, summary, details_json=None):
    """Upsert a progress entry for a phase key.

    If an entry already exists for the given phase, updates it.
    Otherwise inserts a new one. Returns a result dict with ok key.
    """
    now = datetime.now().isoformat()
    existing = db.execute(
        "SELECT id FROM progress_entries WHERE workspace_id = ? AND phase = ?",
        (workspace_id, phase_key)
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
            (workspace_id, phase_key, summary, details_json, now, now)
        )
    return {"ok": True, "phase": phase_key}


def get_progress(db, workspace_id, phase_key=None):
    """Get progress entries with full details. Optionally filter by phase key.

    Returns dict of phase -> {summary, details, created_at, updated_at}.
    """
    if phase_key:
        rows = db.execute(
            "SELECT phase, summary, details_json, created_at, updated_at "
            "FROM progress_entries WHERE workspace_id = ? AND phase = ?",
            (workspace_id, phase_key)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT phase, summary, details_json, created_at, updated_at "
            "FROM progress_entries WHERE workspace_id = ? ORDER BY id",
            (workspace_id,)
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


def get_progress_map(db, workspace_id):
    """Load progress entries into a {phase: summary} dict for compact state views."""
    rows = db.execute(
        "SELECT phase, summary FROM progress_entries WHERE workspace_id = ? ORDER BY id",
        (workspace_id,)
    ).fetchall()
    return {row["phase"]: row["summary"] for row in rows}


def set_impact_analysis(db, workspace_id, analysis_json):
    """Save structured impact analysis JSON to the workspace record."""
    db.execute(
        "UPDATE workspaces SET impact_analysis_json = ? WHERE id = ?",
        (json.dumps(analysis_json), workspace_id)
    )
