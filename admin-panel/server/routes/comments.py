"""Comment CRUD, resolve, and list routes."""
from flask import Blueprint, jsonify, request

from services import comment_service
from services import discussion_service
from core.decorators import with_workspace
from core.i18n import t

bp = Blueprint("comments", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/comments", methods=["POST"])
@with_workspace
def add_comment(db, ws, project):
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


@bp.route("/api/ws/<project_id>/<path:branch>/comments", methods=["GET"])
@with_workspace
def list_comments(db, ws, project):
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


@bp.route("/api/ws/<project_id>/<path:branch>/comments/<int:comment_id>/resolve", methods=["PUT"])
@with_workspace
def resolve_comment(db, ws, project, comment_id):
    body = request.get_json(silent=True) or {}
    resolved = body.get("resolved", True)

    result = comment_service.resolve_comment(db, comment_id, ws["id"], resolved=resolved)
    if "error" in result:
        return jsonify({"error": t("api.error.commentNotFound")}), 404

    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/ws/<project_id>/<path:branch>/discussions/<int:discussion_id>/hide", methods=["PUT"])
@with_workspace
def toggle_discussion_hidden(db, ws, project, discussion_id):
    body = request.get_json(silent=True) or {}
    hidden = body.get("hidden", True)

    result = discussion_service.toggle_hidden(db, discussion_id, ws["id"], hidden=hidden)
    if "error" in result:
        return jsonify({"error": t("api.error.discussionNotFound")}), 404

    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/ws/<project_id>/<path:branch>/comments/<int:comment_id>/reply", methods=["POST"])
@with_workspace
def reply_to_comment(db, ws, project, comment_id):
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

    result = comment_service.post_comment(
        db, ws["id"], text=text, scope=parent["scope"], author=author,
        target=parent["target"], file_path=parent["file_path"],
        parent_id=comment_id,
    )
    db.commit()

    return jsonify({"ok": True, "id": result["id"]})


@bp.route("/api/ws/<project_id>/<path:branch>/discussions", methods=["POST"])
@with_workspace
def add_discussion(db, ws, project):
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
