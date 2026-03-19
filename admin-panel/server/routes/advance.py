"""Phase advancement routes: approve and reject user gates."""
import logging
from flask import Blueprint, jsonify, request

from advance_service import approve_gate, reject_gate
from db import get_db
from helpers import find_workspace
from i18n import t
from terminal import session_name, session_exists, send_keys

logger = logging.getLogger(__name__)

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
    if result.get("status_code", 200) == 200:
        try:
            tmux_name = session_name(project_id, branch)
            exists = session_exists(tmux_name)
            print(f"[TMUX] Approve notification: session={tmux_name}, exists={exists}")
            if exists:
                phase = ws['phase']
                phase_names = {
                    '1.4': 'Preparation review approved. Proceed to planning.',
                    '2.1': 'Plan and scope approved. Proceed to implementation.',
                    '4.2': 'Final approval granted. Proceed to delivery.',
                }
                msg = phase_names.get(phase, '')
                if not msg and phase.endswith('.3'):
                    msg = 'Code review approved for sub-phase ' + phase.replace('.3', '') + '. Proceed to commit.'
                if not msg:
                    msg = 'Phase ' + phase + ' approved. Check workspace_get_state.'
                print(f"[TMUX] Sending to tmux: {msg}")
                send_keys(tmux_name, msg)
            else:
                print(f"[TMUX] WARNING: No tmux session found: {tmux_name}")
        except Exception as e:
            print(f"[TMUX] ERROR: Tmux notification failed: {e}")
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
    if result.get("status_code", 200) == 200:
        try:
            tmux_name = session_name(project_id, branch)
            exists = session_exists(tmux_name)
            print(f"[TMUX] Reject notification: session={tmux_name}, exists={exists}")
            if exists:
                phase = ws['phase']
                phase_names = {
                    '1.4': 'Preparation review rejected. Additional research needed. Check comments.',
                    '2.1': 'Plan rejected. Revise the plan based on feedback. Check comments.',
                    '4.2': 'Final approval rejected. Address issues. Check comments.',
                }
                msg = phase_names.get(phase, '')
                if not msg and phase.endswith('.3'):
                    msg = 'Code review rejected for sub-phase ' + phase.replace('.3', '') + '. Fix issues per comments.'
                if not msg:
                    msg = 'Phase ' + phase + ' rejected. Check workspace_get_comments.'
                print(f"[TMUX] Sending to tmux: {msg}")
                send_keys(tmux_name, msg)
            else:
                print(f"[TMUX] WARNING: No tmux session found: {tmux_name}")
        except Exception as e:
            print(f"[TMUX] ERROR: Tmux notification failed: {e}")
    return jsonify({k: v for k, v in result.items() if k != "status_code"}), result.get("status_code", 200)
