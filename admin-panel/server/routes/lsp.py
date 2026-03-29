"""LSP server management routes: profiles, lifecycle, and WebSocket relay."""
import json
import logging

from flask import Blueprint, jsonify, request
from flask_sock import Sock

from services import lsp_service
from core.decorators import with_workspace
from core.db import get_db_ctx

logger = logging.getLogger(__name__)

bp = Blueprint("lsp", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/lsp/profiles", methods=["GET"])
@with_workspace
def get_profiles(db, ws, project):
    """List LSP-capable profiles assigned to this project."""
    profiles = lsp_service.get_project_lsp_profiles(db, project["id"])
    return jsonify({"profiles": profiles, "project_path": project["path"]})


@bp.route("/api/ws/<project_id>/<path:branch>/lsp/status", methods=["GET"])
@with_workspace
def get_status(db, ws, project):
    """Return running/stopped status for each LSP instance."""
    statuses = lsp_service.get_lsp_status(db, project["id"])
    db.commit()
    return jsonify(statuses)


@bp.route("/api/ws/<project_id>/<path:branch>/lsp/start", methods=["POST"])
@with_workspace
def start_servers(db, ws, project):
    """Start one or all LSP servers.

    Body: optional ``{ "profile_id": N }`` to start a single server.
    Omit profile_id to start all enabled profiles.
    """
    body = request.get_json(silent=True) or {}
    profile_id = body.get("profile_id")
    workspace_path = project["path"]

    if profile_id is not None:
        result = lsp_service.start_lsp_server(db, project["id"], profile_id, workspace_path)
        if "error" in result:
            db.commit()
            return jsonify(result), 400
        db.commit()
        return jsonify(result)

    results = lsp_service.start_all_lsp_servers(db, project["id"], workspace_path)
    return jsonify(results)


@bp.route("/api/ws/<project_id>/<path:branch>/lsp/stop", methods=["POST"])
@with_workspace
def stop_servers(db, ws, project):
    """Stop one or all LSP servers.

    Body: optional ``{ "profile_id": N }`` to stop a single server.
    Omit profile_id to stop all running servers.
    """
    body = request.get_json(silent=True) or {}
    profile_id = body.get("profile_id")

    if profile_id is not None:
        result = lsp_service.stop_lsp_server(db, project["id"], profile_id)
        db.commit()
        return jsonify(result)

    results = lsp_service.stop_all_lsp_servers(db, project["id"])
    return jsonify(results)


@bp.route("/api/ws/<project_id>/<path:branch>/lsp/check-installed", methods=["POST"])
@with_workspace
def check_installed(db, ws, project):
    """Check whether the LSP binary for a profile is installed.

    Body: ``{ "profile_id": N }``
    """
    body = request.get_json(silent=True) or {}
    profile_id = body.get("profile_id")
    if profile_id is None:
        return jsonify({"error": "profile_id is required"}), 400

    profile = db.execute(
        "SELECT * FROM verification_profiles WHERE id = ?", (profile_id,)
    ).fetchone()
    if not profile:
        return jsonify({"error": "profile_not_found"}), 404

    installed = lsp_service.check_lsp_installed(dict(profile))
    return jsonify({"installed": installed})


@bp.route("/api/ws/<project_id>/<path:branch>/lsp/profiles/<int:profile_id>/toggle", methods=["PUT"])
@with_workspace
def toggle_profile(db, ws, project, profile_id):
    """Toggle lsp_enabled for a profile assignment.

    Body: ``{ "enabled": true/false }``
    """
    body = request.get_json(silent=True) or {}
    enabled = body.get("enabled")
    if enabled is None:
        return jsonify({"error": "enabled field is required"}), 400

    row = db.execute(
        "SELECT id FROM project_verification_profiles "
        "WHERE project_id = ? AND profile_id = ?",
        (project["id"], profile_id)
    ).fetchone()
    if not row:
        return jsonify({"error": "profile_assignment_not_found"}), 404

    db.execute(
        "UPDATE project_verification_profiles SET lsp_enabled = ? "
        "WHERE project_id = ? AND profile_id = ?",
        (1 if enabled else 0, project["id"], profile_id)
    )
    db.commit()
    return jsonify({"ok": True, "profile_id": profile_id, "lsp_enabled": bool(enabled)})


def register_lsp_ws(app):
    """Register the LSP WebSocket relay on the Flask app."""
    sock = Sock(app)

    @sock.route("/ws/lsp/<project_id>/<path:branch>")
    def lsp_ws(ws, project_id, branch):
        with get_db_ctx() as db:
            project = db.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if not project:
                ws.send(json.dumps({"error": "project_not_found"}))
                return

        try:
            init_raw = ws.receive(timeout=10)
        except Exception:
            ws.send(json.dumps({"error": "timeout_waiting_for_init"}))
            return

        if init_raw is None:
            return

        try:
            init_msg = json.loads(init_raw)
        except (json.JSONDecodeError, TypeError):
            ws.send(json.dumps({"error": "invalid_json"}))
            return

        default_profile_id = init_msg.get("profile_id")
        ws.send(json.dumps({"ok": True, "status": "connected", "default_profile_id": default_profile_id}))

        while True:
            try:
                raw = ws.receive()
            except Exception:
                break

            if raw is None:
                break

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                ws.send(json.dumps({"error": "invalid_json"}))
                continue

            method = msg.get("method")
            params = msg.get("params", {})
            msg_id = msg.get("id")
            profile_id = msg.get("profile_id", default_profile_id)

            if not method:
                ws.send(json.dumps({"error": "method is required"}))
                continue

            if profile_id is None:
                ws.send(json.dumps({"error": "profile_id is required (in message or init)"}))
                continue

            is_notification = msg_id is None
            if is_notification:
                lsp_service.send_lsp_notification(project_id, profile_id, method, params)
                continue

            result = lsp_service.send_lsp_request(project_id, profile_id, method, params)

            if "error" in result and "jsonrpc" not in result:
                ws.send(json.dumps({"id": msg_id, "error": {"code": -1, "message": result["error"]}}))
                continue

            result["id"] = msg_id
            ws.send(json.dumps(result))
