"""Phase advancement routes: approve and reject user gates."""
import logging
from flask import Blueprint, jsonify, request

from advance_service import approve_gate, reject_gate
from decorators import with_workspace
from i18n import t
from terminal import session_name, session_exists, send_prompt

logger = logging.getLogger(__name__)

bp = Blueprint("advance", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/approve", methods=["POST"])
@with_workspace
def approve(db, ws, project):
    body = request.get_json(silent=True) or {}
    result = approve_gate(ws, body.get("token", ""), body.get("commit_message"))
    if result.get("status_code", 200) == 200:
        try:
            tmux_name = session_name(ws["project_id"], ws["branch"])
            exists = session_exists(tmux_name)
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
                send_prompt(tmux_name, msg)
        except Exception:
            logger.warning("Failed to send tmux approval notification", exc_info=True)
    return jsonify({k: v for k, v in result.items() if k != "status_code"}), result.get("status_code", 200)


@bp.route("/api/ws/<project_id>/<path:branch>/reject", methods=["POST"])
@with_workspace
def reject(db, ws, project):
    body = request.get_json(silent=True) or {}
    result = reject_gate(ws, body.get("token", ""), body.get("comments", ""))
    if result.get("status_code", 200) == 200:
        try:
            tmux_name = session_name(ws["project_id"], ws["branch"])
            exists = session_exists(tmux_name)
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
                send_prompt(tmux_name, msg)
        except Exception:
            logger.warning("Failed to send tmux rejection notification", exc_info=True)
    return jsonify({k: v for k, v in result.items() if k != "status_code"}), result.get("status_code", 200)
