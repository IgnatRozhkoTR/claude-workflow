"""Comment CRUD, resolve, and list routes."""
from datetime import datetime

from flask import Blueprint, jsonify, request

import comment_service
import discussion_service
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
        text = body.get("text", "").strip()

        if not scope or not text:
            return jsonify({"error": t("api.error.scopeAndTextRequired")}), 400

        result = comment_service.post_comment(
            db, ws["id"], text=text, scope=scope,
            author=body.get("author", "user"),
            target=body.get("target", "").strip() or None,
            file_path=body.get("file_path"),
            line_start=body.get("line_start"),
            line_end=body.get("line_end"),
            line_hash=body.get("line_hash"),
        )
        db.commit()

        return jsonify(result)
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

        scope_filter = request.args.get("scope") or None
        resolved_filter = request.args.get("resolved")

        unresolved_only = False
        resolved_only = False
        if resolved_filter == "true":
            resolved_only = True
        elif resolved_filter == "false":
            unresolved_only = True

        comments = comment_service.get_comments(
            db, ws["id"], scope=scope_filter, unresolved_only=unresolved_only
        )

        if resolved_only:
            comments = [c for c in comments if c["resolved"]]

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

        body = request.get_json(silent=True) or {}
        resolved = body.get("resolved", True)

        result = comment_service.resolve_comment(db, comment_id, ws["id"], resolved=resolved)
        if "error" in result:
            return jsonify({"error": t("api.error.commentNotFound")}), 404

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

        body = request.get_json(silent=True) or {}
        hidden = body.get("hidden", True)

        result = discussion_service.toggle_hidden(db, discussion_id, ws["id"], hidden=hidden)
        if "error" in result:
            return jsonify({"error": t("api.error.discussionNotFound")}), 404

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

        result = discussion_service.post_discussion(
            db, ws["id"], text,
            author="user",
            disc_type=disc_type,
            parent_id=parent_id,
        )
        if "error" in result:
            return jsonify({"error": t("api.error.discussionNotFound")}), 404
        db.commit()

        return jsonify({"ok": True, "id": result["id"]})
    finally:
        db.close()
