"""Improvement tracking service — global (not workspace-scoped)."""
from datetime import datetime


def report_improvement(db, scope, title, description, context=None):
    """Save a new improvement suggestion."""
    cursor = db.execute(
        "INSERT INTO improvements (scope, title, description, context, status, created_at) "
        "VALUES (?, ?, ?, ?, 'open', ?)",
        (scope, title.strip(), description.strip(), context.strip() if context else None, datetime.now().isoformat())
    )
    return {"ok": True, "id": cursor.lastrowid}


def get_improvements(db, scope=None, status=None):
    """List improvements, optionally filtered by scope and/or status."""
    query = "SELECT * FROM improvements WHERE 1=1"
    params = []
    if scope:
        query += " AND scope = ?"
        params.append(scope)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def resolve_improvement(db, improvement_id, note=None):
    """Mark an improvement as resolved."""
    row = db.execute("SELECT id FROM improvements WHERE id = ?", (improvement_id,)).fetchone()
    if not row:
        return {"error": "not_found"}
    db.execute(
        "UPDATE improvements SET status = 'resolved', resolved_note = ?, resolved_at = ? WHERE id = ?",
        (note.strip() if note else None, datetime.now().isoformat(), improvement_id)
    )
    return {"ok": True}


def reopen_improvement(db, improvement_id):
    """Re-open a resolved improvement."""
    row = db.execute("SELECT id FROM improvements WHERE id = ?", (improvement_id,)).fetchone()
    if not row:
        return {"error": "not_found"}
    db.execute(
        "UPDATE improvements SET status = 'open', resolved_note = NULL, resolved_at = NULL WHERE id = ?",
        (improvement_id,)
    )
    return {"ok": True}
