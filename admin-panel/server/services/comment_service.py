"""Comment and review domain logic: get, post, resolve comments and review issues.

All comment/review business logic lives here. MCP tools and route handlers are thin
wrappers that delegate to this module.
"""
from datetime import datetime

from core.i18n import t


def load_replies(db, parent_id):
    """Load reply discussions for a given parent comment/discussion."""
    rows = db.execute(
        "SELECT id, text, author, created_at, status, resolved_at "
        "FROM discussions WHERE parent_id = ? ORDER BY id",
        (parent_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_comments(db, workspace_id, scope=None, unresolved_only=False):
    """Get scoped comments with optional scope filter and unresolved-only flag.

    Returns a list of comment dicts, each with a 'replies' sub-list.
    """
    query = (
        "SELECT id, parent_id, scope, target, file_path, line_start, line_end, line_hash, "
        "text, author, type, created_at, status, resolved_at, resolution "
        "FROM discussions WHERE workspace_id = ? AND scope IS NOT NULL AND parent_id IS NULL"
    )
    params = [workspace_id]

    if scope:
        query += " AND scope = ?"
        params.append(scope)

    if unresolved_only:
        query += " AND status = 'open'"

    query += " ORDER BY id"

    rows = db.execute(query, params).fetchall()
    comments = []
    for row in rows:
        comment = {
            "id": row["id"],
            "parent_id": row["parent_id"],
            "scope": row["scope"],
            "target": row["target"],
            "file_path": row["file_path"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "line_hash": row["line_hash"],
            "text": row["text"],
            "author": row["author"],
            "type": row["type"],
            "created_at": row["created_at"],
            "resolved": row["status"] == "resolved",
            "resolved_at": row["resolved_at"],
            "resolution": row["resolution"],
        }
        comment["replies"] = load_replies(db, row["id"])
        comments.append(comment)
    return comments


def post_comment(db, workspace_id, text, scope, author="user",
                 target=None, file_path=None, line_start=None, line_end=None,
                 line_hash=None, parent_id=None):
    """Insert a scoped comment into the discussions table.

    When parent_id is set, the row is a reply to an existing scoped comment.
    Returns a result dict with ok/id keys.
    """
    resolution = "open" if scope == "review" else None
    cursor = db.execute(
        "INSERT INTO discussions "
        "(workspace_id, parent_id, scope, target, file_path, line_start, line_end, line_hash, "
        "text, author, status, resolution, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)",
        (workspace_id, parent_id, scope, target, file_path, line_start, line_end, line_hash,
         text, author, resolution, datetime.now().isoformat())
    )
    return {"ok": True, "id": cursor.lastrowid}


def resolve_comment(db, comment_id, workspace_id, resolved=True, block_review_scope=False, locale="en"):
    """Resolve or unresolve a comment by ID.

    When block_review_scope=True and the comment has scope='review', returns an i18n error.
    When resolved=False, clears resolved_at and sets status back to 'open'.

    Returns a result dict: {"ok": True, "comment_id": ..., "resolved": bool} on success,
    {"error": ...} on failure.
    """
    comment = db.execute(
        "SELECT id, scope FROM discussions WHERE id = ? AND workspace_id = ? AND scope IS NOT NULL",
        (comment_id, workspace_id)
    ).fetchone()
    if not comment:
        return {"error": t("mcp.error.commentNotFound", locale, comment_id=comment_id)}

    if block_review_scope and comment["scope"] == "review":
        return {"error": t("mcp.error.reviewScopeResolveBlocked", locale)}

    if resolved:
        db.execute(
            "UPDATE discussions SET status = 'resolved', resolved_at = ? WHERE id = ?",
            (datetime.now().isoformat(), comment_id)
        )
    else:
        db.execute(
            "UPDATE discussions SET status = 'open', resolved_at = NULL WHERE id = ?",
            (comment_id,)
        )
    return {"ok": True, "comment_id": comment_id, "resolved": resolved}


def submit_review_issue(db, workspace_id, file_path, line_start, line_end,
                        description, author="reviewer"):
    """Insert a code review finding as a scope='review' discussion.

    Returns a result dict with ok/id keys.
    """
    cursor = db.execute(
        "INSERT INTO discussions "
        "(workspace_id, scope, target, file_path, line_start, line_end, "
        "text, author, status, resolution, created_at) "
        "VALUES (?, 'review', ?, ?, ?, ?, ?, ?, 'open', 'open', ?)",
        (workspace_id, file_path.strip(), file_path.strip(),
         line_start, line_end, description.strip(), author, datetime.now().isoformat())
    )
    return {"ok": True, "id": cursor.lastrowid}


def get_review_issues(db, workspace_id, resolution=None):
    """Get all scope='review' discussion items with optional resolution filter.

    Returns a list of review issue dicts.
    """
    query = (
        "SELECT id, file_path, line_start, line_end, text, resolution, author, status, created_at "
        "FROM discussions WHERE workspace_id = ? AND scope = 'review' AND parent_id IS NULL"
    )
    params = [workspace_id]
    if resolution:
        query += " AND resolution = ?"
        params.append(resolution)
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


def resolve_review_issue(db, issue_id, workspace_id, resolution, locale="en"):
    """Set the resolution on a scope='review' discussion item.

    Returns a result dict with ok/error keys.
    """
    row = db.execute(
        "SELECT id FROM discussions WHERE id = ? AND workspace_id = ? AND scope = 'review'",
        (issue_id, workspace_id)
    ).fetchone()
    if not row:
        return {"error": t("mcp.error.reviewIssueNotFound", locale, issue_id=issue_id)}

    db.execute(
        "UPDATE discussions SET resolution = ? WHERE id = ?",
        (resolution, issue_id)
    )
    return {"ok": True, "issue_id": issue_id, "resolution": resolution}
