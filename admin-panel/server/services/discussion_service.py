"""General discussion domain logic: post, list, update, reply, toggle hidden, delete.

Handles discussions where scope IS NULL (general/research). Scoped comments
(scope IS NOT NULL) are handled by comment_service.

All general-discussion business logic lives here. MCP tools and route handlers
are thin wrappers that delegate to this module.
"""
from datetime import datetime

from services.comment_service import load_replies


def post_discussion(db, workspace_id, text, author="user", disc_type="general",
                    parent_id=None, scope=None, target=None):
    """Insert a discussion (root or reply, general or scoped).

    When parent_id is set, validates that the parent exists in the same workspace.
    When scope is set, the discussion is scoped (e.g. attached to a phase/target).
    Returns a result dict with ok/id or error key.
    """
    resolved_parent_id = parent_id if parent_id else None

    if resolved_parent_id:
        parent = db.execute(
            "SELECT id FROM discussions WHERE id = ? AND workspace_id = ?",
            (resolved_parent_id, workspace_id)
        ).fetchone()
        if not parent:
            return {"error": "parent_not_found", "parent_id": resolved_parent_id}

    cursor = db.execute(
        "INSERT INTO discussions (workspace_id, parent_id, text, author, type, scope, target, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
        (workspace_id, resolved_parent_id, text, author, disc_type, scope, target,
         datetime.now().isoformat())
    )
    return {"ok": True, "id": cursor.lastrowid}


def list_discussions(db, workspace_id, include_hidden=True, open_only=False):
    """Load general discussions (scope IS NULL, parent_id IS NULL) with replies.

    When open_only=True, only returns discussions with status='open'.
    Returns a list of discussion dicts, each with a 'replies' sub-list.
    """
    query = (
        "SELECT id, parent_id, text, author, status, type, hidden, created_at, resolved_at "
        "FROM discussions WHERE workspace_id = ? AND scope IS NULL AND parent_id IS NULL"
    )
    params = [workspace_id]

    if not include_hidden:
        query += " AND (hidden IS NULL OR hidden = 0)"

    if open_only:
        query += " AND status = 'open'"

    query += " ORDER BY id"

    rows = db.execute(query, params).fetchall()
    discussions = []
    for row in rows:
        d = dict(row)
        d["replies"] = load_replies(db, row["id"])
        discussions.append(d)
    return discussions


def update_discussion(db, discussion_id, workspace_id, text=None, status=None):
    """Update text and/or status on a discussion.

    When status is set to 'resolved', also sets resolved_at timestamp.
    Returns a result dict with ok/error key.
    """
    row = db.execute(
        "SELECT id FROM discussions WHERE id = ? AND workspace_id = ?",
        (discussion_id, workspace_id)
    ).fetchone()
    if not row:
        return {"error": "discussion_not_found"}

    updates = []
    params = []
    if text is not None:
        updates.append("text = ?")
        params.append(text)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
        if status == "resolved":
            updates.append("resolved_at = ?")
            params.append(datetime.now().isoformat())

    if not updates:
        return {"ok": True}

    params.append(discussion_id)
    db.execute(f"UPDATE discussions SET {', '.join(updates)} WHERE id = ?", params)
    return {"ok": True}


def toggle_hidden(db, discussion_id, workspace_id, hidden=True):
    """Toggle the hidden flag on a root general discussion.

    Only operates on scope IS NULL, parent_id IS NULL discussions.
    Returns a result dict with ok/error key.
    """
    disc = db.execute(
        "SELECT id FROM discussions WHERE id = ? AND workspace_id = ? AND scope IS NULL AND parent_id IS NULL",
        (discussion_id, workspace_id)
    ).fetchone()
    if not disc:
        return {"error": "discussion_not_found"}

    hidden_val = 1 if hidden else 0
    db.execute("UPDATE discussions SET hidden = ? WHERE id = ?", (hidden_val, discussion_id))
    return {"ok": True}


def delete_discussion(db, discussion_id, workspace_id):
    """Delete a discussion by ID. Returns True if deleted, False if not found."""
    rows = db.execute(
        "DELETE FROM discussions WHERE id = ? AND workspace_id = ?",
        (discussion_id, workspace_id)
    ).rowcount
    return rows > 0
