"""Hook API routes for migrated Python hooks.

Provides endpoints that replace direct SQLite queries in shell hooks.
Called on every tool use, so performance matters.
"""
import os

from flask import Blueprint, jsonify, request

from core.db import get_db, ws_field
from advance import permissions as permission_service

bp = Blueprint("hook_api", __name__)


def _resolve_workspace(db, cwd):
    """Find active workspace by walking up from cwd."""
    path = os.path.abspath(cwd)
    workspaces = db.execute(
        "SELECT * FROM workspaces WHERE status = 'active'"
    ).fetchall()

    while True:
        for ws in workspaces:
            if os.path.abspath(ws["working_dir"]) == path:
                return ws
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


@bp.route("/api/hook/check-permission", methods=["POST"])
def check_permission():
    """Check whether a tool invocation is allowed in the current workspace state.

    Replaces all direct SQLite queries from the shell-based pre-tool hook.
    """
    body = request.get_json(silent=True) or {}
    cwd = body.get("cwd", ".")
    tool_name = body.get("tool_name", "")

    db = get_db()
    try:
        ws = _resolve_workspace(db, cwd)
        if not ws:
            return jsonify({"governed": False, "allowed": True})

        if ws_field(ws, "yolo_mode", 0):
            return jsonify({"governed": True, "allowed": True})

        tool_input = {
            "file_path": body.get("file_path", ""),
            "command": body.get("command", ""),
        }
        return jsonify(permission_service.check_tool_permission(ws, tool_name, tool_input, cwd))
    finally:
        db.close()


@bp.route("/api/hook/session-context", methods=["GET"])
def session_context():
    """Return workspace context for the session-start banner."""
    cwd = request.args.get("cwd", ".")

    db = get_db()
    try:
        ws = _resolve_workspace(db, cwd)
        if not ws:
            return jsonify({"found": False})

        research_rows = db.execute(
            "SELECT topic, proven FROM research_entries WHERE workspace_id = ? ORDER BY id",
            (ws["id"],)
        ).fetchall()
        research = [{"topic": row["topic"], "proven": row["proven"]} for row in research_rows]

        return jsonify({
            "found": True,
            "branch": ws["branch"],
            "phase": ws["phase"],
            "working_dir": ws["working_dir"],
            "research": research,
        })
    finally:
        db.close()
