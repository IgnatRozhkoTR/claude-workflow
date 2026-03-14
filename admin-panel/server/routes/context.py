"""Workspace context routes: ticket info, discussions, and path search."""
import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from db import get_db
from helpers import find_workspace, run_git
from i18n import t

bp = Blueprint("context", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/context", methods=["GET"])
def get_context(project_id, branch):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        discussions = db.execute(
            "SELECT id, parent_id, text, author, status, type, hidden, created_at, resolved_at "
            "FROM discussions WHERE workspace_id = ? AND scope IS NULL AND parent_id IS NULL ORDER BY id",
            (ws["id"],)
        ).fetchall()

        discussions_list = []
        for row in discussions:
            d = dict(row)
            replies = db.execute(
                "SELECT id, text, author, status, created_at, resolved_at "
                "FROM discussions WHERE parent_id = ? ORDER BY id",
                (row["id"],)
            ).fetchall()
            d["replies"] = [dict(r) for r in replies]
            discussions_list.append(d)

        return jsonify({
            "ticket_id": ws["ticket_id"] or ws["branch"],
            "ticket_name": ws["ticket_name"] or "",
            "context": ws["context_text"] or "",
            "refs": json.loads(ws["context_refs_json"] or "[]"),
            "discussions": discussions_list,
        })
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/context", methods=["PUT"])
def update_context(project_id, branch):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        body = request.json
        updates = []
        params = []
        if "ticket_name" in body:
            updates.append("ticket_name = ?")
            params.append(body["ticket_name"])
        if "context" in body:
            updates.append("context_text = ?")
            params.append(body["context"])
        if "ticket_id" in body:
            updates.append("ticket_id = ?")
            params.append(body["ticket_id"])
        if "refs" in body:
            refs = body["refs"]
            if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
                return jsonify({"error": t("api.error.refsMustBeListOfStrings")}), 400
            updates.append("context_refs_json = ?")
            params.append(json.dumps(refs))

        if updates:
            params.append(ws["id"])
            db.execute(f"UPDATE workspaces SET {', '.join(updates)} WHERE id = ?", params)
            db.commit()

        return jsonify({"ok": True})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/context/discussions", methods=["POST"])
def add_discussion(project_id, branch):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        body = request.json
        topic = body.get("topic") or body.get("text")
        if not topic:
            return jsonify({"error": t("api.error.topicRequired")}), 400

        parent_id = body.get("parent_id")
        disc_type = body.get("type", "general")

        cursor = db.execute(
            "INSERT INTO discussions (workspace_id, parent_id, text, author, type, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (ws["id"], parent_id, topic, body.get("author", "user"),
             disc_type, datetime.now().isoformat())
        )
        db.commit()

        return jsonify({"ok": True, "id": cursor.lastrowid})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/context/discussions/<int:discussion_id>", methods=["PUT"])
def update_discussion(project_id, branch, discussion_id):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        row = db.execute(
            "SELECT id FROM discussions WHERE id = ? AND workspace_id = ?",
            (discussion_id, ws["id"])
        ).fetchone()
        if not row:
            return jsonify({"error": t("api.error.discussionNotFound")}), 404

        body = request.json
        updates = []
        params = []
        if "text" in body:
            updates.append("text = ?")
            params.append(body["text"])
        if "status" in body:
            updates.append("status = ?")
            params.append(body["status"])
            if body["status"] == "resolved":
                updates.append("resolved_at = ?")
                params.append(datetime.now().isoformat())

        if updates:
            params.append(discussion_id)
            db.execute(f"UPDATE discussions SET {', '.join(updates)} WHERE id = ?", params)
            db.commit()

        return jsonify({"ok": True})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/context/discussions/<int:discussion_id>/reply", methods=["POST"])
def reply_to_discussion(project_id, branch, discussion_id):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        parent = db.execute(
            "SELECT id FROM discussions WHERE id = ? AND workspace_id = ?",
            (discussion_id, ws["id"])
        ).fetchone()
        if not parent:
            return jsonify({"error": t("api.error.discussionNotFound")}), 404

        body = request.json
        text = body.get("text", "").strip()
        if not text:
            return jsonify({"error": t("api.error.textRequired")}), 400

        cursor = db.execute(
            "INSERT INTO discussions (workspace_id, parent_id, text, author, status, created_at) "
            "VALUES (?, ?, ?, ?, 'open', ?)",
            (ws["id"], discussion_id, text, body.get("author", "user"), datetime.now().isoformat())
        )
        db.commit()
        return jsonify({"ok": True, "id": cursor.lastrowid})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/search-paths", methods=["GET"])
def search_paths(project_id, branch):
    """Search for files and directories matching a query string for autocomplete."""
    q = request.args.get("q", "").strip().lower()
    if not q or len(q) < 2:
        return jsonify({"results": []})

    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404
        working_dir = ws["working_dir"]
    finally:
        db.close()

    ok, stdout, _ = run_git(working_dir, "ls-files")
    if not ok:
        return jsonify({"results": []})

    files = [f.strip() for f in stdout.splitlines() if f.strip()]

    matches = set()
    for f in files:
        f_lower = f.lower()
        if q in f_lower:
            matches.add(f)
        parts = f.split("/")
        for i in range(1, len(parts)):
            dir_path = "/".join(parts[:i])
            if q in dir_path.lower():
                matches.add(dir_path + "/")

    sorted_matches = sorted(matches, key=lambda x: (not x.endswith("/"), x))

    return jsonify({"results": sorted_matches[:30]})


@bp.route("/api/ws/<project_id>/<path:branch>/context/discussions/<int:discussion_id>", methods=["DELETE"])
def delete_discussion(project_id, branch, discussion_id):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        rows = db.execute(
            "DELETE FROM discussions WHERE id = ? AND workspace_id = ?",
            (discussion_id, ws["id"])
        ).rowcount
        db.commit()

        if rows == 0:
            return jsonify({"error": t("api.error.discussionNotFound")}), 404

        return jsonify({"ok": True})
    finally:
        db.close()
