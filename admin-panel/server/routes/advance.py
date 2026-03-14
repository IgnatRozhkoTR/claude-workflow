"""Phase advancement routes: approve and reject user gates."""
from flask import Blueprint, jsonify, request

from advance_service import approve_gate, reject_gate
from db import get_db
from helpers import find_workspace
from i18n import t

bp = Blueprint("advance", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/approve", methods=["POST"])
def approve(project_id, branch):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404
    finally:
        db.close()

    body = request.get_json(silent=True) or {}
    result = approve_gate(ws, body.get("token", ""), body.get("commit_message"))
    return jsonify({k: v for k, v in result.items() if k != "status_code"}), result.get("status_code", 200)


@bp.route("/api/ws/<project_id>/<path:branch>/reject", methods=["POST"])
def reject(project_id, branch):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404
    finally:
        db.close()

    body = request.get_json(silent=True) or {}
    result = reject_gate(ws, body.get("token", ""), body.get("comments", ""))
    return jsonify({k: v for k, v in result.items() if k != "status_code"}), result.get("status_code", 200)
