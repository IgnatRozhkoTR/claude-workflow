"""Comment CRUD, resolve, and list routes."""
from datetime import datetime

from flask import Blueprint, jsonify, request

from db import get_db
from helpers import find_workspace
from i18n import t

bp = Blueprint("comments", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/comments", methods=["POST"])
def add_comment(project_id, branch):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        body = request.get_json(silent=True) or {}
        scope = body.get("scope", "").strip()
        target = body.get("target", "").strip()
        text = body.get("text", "").strip()
        file_path = body.get("file_path")
        line_start = body.get("line_start")
        line_end = body.get("line_end")
        line_hash = body.get("line_hash")
        author = body.get("author", "user")

        if not scope or not text:
            return jsonify({"error": t("api.error.scopeAndTextRequired")}), 400

        resolution = 'open' if scope == 'review' else None
        cursor = db.execute(
            "INSERT INTO discussions "
            "(workspace_id, scope, target, file_path, line_start, line_end, line_hash, "
            "text, author, status, resolution, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)",
            (ws["id"], scope, target, file_path, line_start, line_end, line_hash,
             text, author, resolution, datetime.now().isoformat())
        )
        db.commit()

        return jsonify({"ok": True, "id": cursor.lastrowid})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/comments", methods=["GET"])
def list_comments(project_id, branch):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        query = (
            "SELECT id, parent_id, scope, target, file_path, line_start, line_end, line_hash, "
            "text, author, type, created_at, status, resolved_at, resolution "
            "FROM discussions WHERE workspace_id = ? AND scope IS NOT NULL AND parent_id IS NULL"
        )
        params = [ws["id"]]

        scope_filter = request.args.get("scope")
        if scope_filter:
            query += " AND scope = ?"
            params.append(scope_filter)

        resolved_filter = request.args.get("resolved")
        if resolved_filter == "true":
            query += " AND status = 'resolved'"
        elif resolved_filter == "false":
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
            replies = db.execute(
                "SELECT id, text, author, created_at, status, resolved_at "
                "FROM discussions WHERE parent_id = ? ORDER BY id",
                (row["id"],)
            ).fetchall()
            comment["replies"] = [dict(r) for r in replies]
            comments.append(comment)

        return jsonify({"comments": comments})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/comments/<int:comment_id>/resolve", methods=["PUT"])
def resolve_comment(project_id, branch, comment_id):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        comment = db.execute(
            "SELECT * FROM discussions WHERE id = ? AND workspace_id = ?",
            (comment_id, ws["id"])
        ).fetchone()
        if not comment:
            return jsonify({"error": t("api.error.commentNotFound")}), 404

        body = request.get_json(silent=True) or {}
        resolved = body.get("resolved", True)

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
        db.commit()

        return jsonify({"ok": True})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/discussions/<int:discussion_id>/hide", methods=["PUT"])
def toggle_discussion_hidden(project_id, branch, discussion_id):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        disc = db.execute(
            "SELECT * FROM discussions WHERE id = ? AND workspace_id = ? AND scope IS NULL AND parent_id IS NULL",
            (discussion_id, ws["id"])
        ).fetchone()
        if not disc:
            return jsonify({"error": t("api.error.discussionNotFound")}), 404

        body = request.get_json(silent=True) or {}
        hidden = 1 if body.get("hidden", True) else 0

        db.execute("UPDATE discussions SET hidden = ? WHERE id = ?", (hidden, discussion_id))
        db.commit()

        return jsonify({"ok": True})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/comments/<int:comment_id>/reply", methods=["POST"])
def reply_to_comment(project_id, branch, comment_id):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        parent = db.execute(
            "SELECT * FROM discussions WHERE id = ? AND workspace_id = ? AND scope IS NOT NULL",
            (comment_id, ws["id"])
        ).fetchone()
        if not parent:
            return jsonify({"error": t("api.error.commentNotFound")}), 404

        body = request.get_json(silent=True) or {}
        text = body.get("text", "").strip()
        author = body.get("author", "user")

        if not text:
            return jsonify({"error": t("api.error.textRequired")}), 400

        cursor = db.execute(
            "INSERT INTO discussions "
            "(workspace_id, parent_id, scope, target, file_path, text, author, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
            (ws["id"], comment_id, parent["scope"], parent["target"], parent["file_path"],
             text, author, datetime.now().isoformat())
        )
        db.commit()

        return jsonify({"ok": True, "id": cursor.lastrowid})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/discussions", methods=["POST"])
def add_discussion(project_id, branch):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        body = request.get_json(silent=True) or {}
        text = body.get("text", "").strip()
        disc_type = body.get("type", "general")
        parent_id = body.get("parent_id")

        if not text:
            return jsonify({"error": t("api.error.textRequired")}), 400
        if disc_type not in ("general", "research"):
            return jsonify({"error": t("api.error.invalidDiscussionType")}), 400

        cursor = db.execute(
            "INSERT INTO discussions (workspace_id, parent_id, text, author, type, status, created_at) "
            "VALUES (?, ?, ?, 'user', ?, 'open', ?)",
            (ws["id"], parent_id, text, disc_type, datetime.now().isoformat())
        )
        db.commit()

        return jsonify({"ok": True, "id": cursor.lastrowid})
    finally:
        db.close()
