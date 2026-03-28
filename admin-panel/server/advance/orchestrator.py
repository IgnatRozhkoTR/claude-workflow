"""Phase advancement orchestrator using Phase objects.

Replaces hardcoded phase string routing with Phase registry lookups.
All business logic (gate nonce verification, guard evaluation, transitions,
yolo auto-approve) is preserved exactly from advance/service.py.
"""
import logging
import secrets
from datetime import datetime

from advance.guards import GUARD_ORCHESTRATOR
from advance.phases import get_phase
from core.db import get_db_ctx, ws_field
from core.i18n import t
from core.terminal import notify_workspace

logger = logging.getLogger(__name__)


def is_user_gate(phase_str: str) -> bool:
    """Check whether a phase requires explicit user approval."""
    phase = get_phase(phase_str)
    return phase.is_user_gate if phase else False


def check_progress(workspace_id, phase_key):
    """Verify that a progress entry exists for the given phase key."""
    with get_db_ctx() as db:
        row = db.execute(
            "SELECT summary FROM progress_entries WHERE workspace_id = ? AND phase = ?",
            (workspace_id, phase_key)
        ).fetchone()
        return bool(row and row["summary"].strip())


def transition_phase(db, ws, new_phase, clear_nonce=False, commit_hash=None):
    """Shared phase transition: update phase, record history, manage nonce.

    Returns True if the transition succeeded, False if the phase was already changed
    by a concurrent request (optimistic lock via WHERE phase = current).
    """
    rows = db.execute(
        "UPDATE workspaces SET phase = ? WHERE id = ? AND phase = ?",
        (new_phase, ws["id"], ws["phase"])
    ).rowcount
    if rows == 0:
        return False

    db.execute(
        "INSERT INTO phase_history (workspace_id, from_phase, to_phase, time, commit_hash) VALUES (?, ?, ?, ?, ?)",
        (ws["id"], ws["phase"], new_phase, datetime.now().isoformat(), commit_hash)
    )

    if clear_nonce:
        db.execute("UPDATE workspaces SET gate_nonce = NULL WHERE id = ?", (ws["id"],))
    elif is_user_gate(new_phase):
        nonce = secrets.token_urlsafe(32)
        db.execute("UPDATE workspaces SET gate_nonce = ? WHERE id = ?", (nonce, ws["id"]))

    return True


def _notify_yolo_approve(ws, phase):
    """Send a YOLO auto-approval notification to the tmux session."""
    try:
        from core.terminal import send_prompt, session_name, session_exists
        name = session_name(ws["project_id"], ws["sanitized_branch"])
        if session_exists(name):
            send_prompt(name, f"[YOLO] Auto-approved phase {phase}. Proceeding.")
    except Exception:
        logger.warning("Failed to send YOLO auto-approve notification", exc_info=True)


def approve_gate(ws, token, commit_message=None):
    """Approve a user gate. Returns a result dict with an embedded status_code key."""
    locale = ws["locale"]
    phase_str = ws["phase"]

    phase = get_phase(phase_str)
    if not phase or not phase.is_user_gate:
        return {"error": t("gate.error.notAtUserGate", locale), "status_code": 400}

    if not token:
        return {"error": t("gate.error.nonceRequired", locale), "status_code": 400}
    if token != ws["gate_nonce"]:
        return {"error": t("gate.error.invalidNonce", locale), "status_code": 403}

    yolo_mode = ws_field(ws, "yolo_mode", 0)
    if not yolo_mode:
        guard_results = GUARD_ORCHESTRATOR.evaluate_all(phase_str, ws, {})
        rejected = [r for r in guard_results if r["status"] == "rejected"]
        if rejected:
            return {"error": rejected[0]["message"], "guard_errors": rejected, "status_code": 422}

    new_phase = phase.approve_target
    if not new_phase:
        return {"error": t("gate.error.unknownGate", locale), "status_code": 400}

    with get_db_ctx() as db:
        phase.on_approve(ws, {"commit_message": commit_message} if commit_message else {}, db)

        if not transition_phase(db, ws, new_phase, clear_nonce=True):
            return {"error": t("gate.error.phaseAlreadyChanged", locale), "status_code": 409}

        db.commit()
        return {"phase": new_phase, "previous_phase": phase_str, "status": "ok", "status_code": 200}


def reject_gate(ws, token, comments=""):
    """Reject a user gate. Returns a result dict with an embedded status_code key."""
    locale = ws["locale"]
    phase_str = ws["phase"]

    phase = get_phase(phase_str)
    if not phase or not phase.is_user_gate:
        return {"error": t("gate.error.notAtUserGate", locale), "status_code": 400}

    if not token:
        return {"error": t("gate.error.nonceRequired", locale), "status_code": 400}
    if token != ws["gate_nonce"]:
        return {"error": t("gate.error.invalidNonce", locale), "status_code": 403}

    new_phase = phase.reject_target
    if not new_phase:
        return {"error": t("gate.error.unknownGate", locale), "status_code": 400}

    with get_db_ctx() as db:
        if not transition_phase(db, ws, new_phase, clear_nonce=True):
            return {"error": t("gate.error.phaseAlreadyChanged", locale), "status_code": 409}

        if comments:
            db.execute(
                "INSERT INTO discussions (workspace_id, scope, target, text, author, status, created_at) "
                "VALUES (?, 'phase', ?, ?, 'user', 'open', ?)",
                (ws["id"], f"reject:{phase_str}", comments, datetime.now().isoformat())
            )

        db.commit()
        return {"phase": new_phase, "previous_phase": phase_str, "status": "rejected", "status_code": 200}


def perform_advance(ws, project_path, body=None):
    """Core advance logic. Returns (result_dict, http_status_code).

    Can be called from Flask route or MCP tool.
    Manages its own DB connection for the transaction.
    """
    body = body or {}
    phase_str = ws["phase"]
    locale = ws["locale"]

    phase = get_phase(phase_str)
    if not phase:
        return {"error": t("advance.error.noAdvancerForPhase", locale, phase=phase_str)}, 400

    if phase.is_user_gate:
        yolo = ws_field(ws, "yolo_mode", 0)
        if yolo:
            nonce = ws["gate_nonce"]
            if nonce:
                result = approve_gate(ws, nonce)
                status_code = result.pop("status_code", 200)
                if status_code == 200:
                    _notify_yolo_approve(ws, phase_str)
                    return result, status_code
        return {"error": t("advance.error.awaitingUserApproval", locale), "phase": phase_str}, 409

    ok, details = phase.validate(ws, body, project_path)
    if not ok:
        return {"phase": phase_str, "status": "blocked", **details}, 422

    required_key = phase.progress_key(ws)
    if required_key and not check_progress(ws["id"], required_key):
        return {
            "phase": phase_str,
            "status": "blocked",
            "message": t("advance.error.noProgress", locale, phase=required_key, next=phase.next_phase(ws)),
        }, 422

    yolo_mode = ws_field(ws, "yolo_mode", 0)
    if not yolo_mode:
        guard_results = GUARD_ORCHESTRATOR.evaluate_all(phase_str, ws, body)
        rejected = [r for r in guard_results if r["status"] == "rejected"]
        if rejected:
            return {"phase": phase_str, "status": "blocked", "guard_errors": rejected}, 422

    new_phase = phase.next_phase(ws)

    with get_db_ctx() as db:
        if not transition_phase(db, ws, new_phase, commit_hash=body.get("commit_hash")):
            return {"error": t("advance.error.phaseAlreadyChanged", locale)}, 409

        db.commit()

        yolo_enabled = ws_field(ws, "yolo_mode", 0)
        if is_user_gate(new_phase) and yolo_enabled:
            ws_fresh = db.execute(
                "SELECT * FROM workspaces WHERE project_id = ? AND sanitized_branch = ?",
                (ws["project_id"], ws["sanitized_branch"])
            ).fetchone()
            nonce = ws_fresh["gate_nonce"] if ws_fresh else None
            if nonce:
                approve_result = approve_gate(ws_fresh, nonce)
                approve_status = approve_result.pop("status_code", 200)
                if approve_status == 200:
                    _notify_yolo_approve(ws_fresh, new_phase)
                    return approve_result, approve_status

        code = 202 if is_user_gate(new_phase) else 200
        result = {
            "phase": new_phase,
            "previous_phase": phase_str,
            "message": phase.success_message(ws, new_phase),
            "status": "awaiting_approval" if code == 202 else "ok",
        }
        if code == 202:
            notify_workspace(ws, "Phase requires your approval. Check the admin panel.")
        return result, code
