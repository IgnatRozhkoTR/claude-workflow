"""Phase advancement routes: approve and reject user gates."""
import logging
from flask import Blueprint, jsonify, request

from advance.orchestrator import approve_gate, reject_gate
from core.decorators import with_workspace
from core.i18n import t
from core.terminal import notify_workspace

logger = logging.getLogger(__name__)

bp = Blueprint("advance", __name__)

_APPROVE_MESSAGES = {
    '1.4': 'Preparation review approved. Proceed to planning.',
    '4.2': 'Final approval granted. Proceed to delivery.',
}

_REJECT_MESSAGES = {
    '1.4': 'Preparation review rejected. Additional research needed. Check comments.',
    '4.2': 'Final approval rejected. Address issues. Check comments.',
}


def _build_gate_message(phase, phase_messages, fallback_sub_approved, fallback_generic):
    msg = phase_messages.get(phase, '')
    if not msg and phase.endswith('.3'):
        sub = phase.replace('.3', '')
        msg = fallback_sub_approved.format(sub=sub)
    if not msg:
        msg = fallback_generic.format(phase=phase)
    return msg


@bp.route("/api/ws/<project_id>/<path:branch>/approve", methods=["POST"])
@with_workspace
def approve(db, ws, project):
    body = request.get_json(silent=True) or {}
    result = approve_gate(ws, body.get("token", ""), body.get("commit_message"))
    if result.get("status_code", 200) == 200:
        msg = _build_gate_message(
            ws['phase'], _APPROVE_MESSAGES,
            'Code review approved for sub-phase {sub}. Proceed to commit.',
            'Phase {phase} approved. Check workspace_get_state.',
        )
        notify_workspace(ws, msg)
    return jsonify({k: v for k, v in result.items() if k != "status_code"}), result.get("status_code", 200)


@bp.route("/api/ws/<project_id>/<path:branch>/reject", methods=["POST"])
@with_workspace
def reject(db, ws, project):
    body = request.get_json(silent=True) or {}
    result = reject_gate(ws, body.get("token", ""), body.get("comments", ""))
    if result.get("status_code", 200) == 200:
        msg = _build_gate_message(
            ws['phase'], _REJECT_MESSAGES,
            'Code review rejected for sub-phase {sub}. Fix issues per comments.',
            'Phase {phase} rejected. Check workspace_get_comments.',
        )
        notify_workspace(ws, msg)
    return jsonify({k: v for k, v in result.items() if k != "status_code"}), result.get("status_code", 200)
