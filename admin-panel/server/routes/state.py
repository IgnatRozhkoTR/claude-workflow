"""Workspace state routes: phase, scope, plan, progress."""
import json
import logging
import re
from datetime import datetime

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

from core.db import get_db, get_db_ctx, ws_field
from services import comment_service
from services import discussion_service
from core.codex import maybe_start_codex_review_for_workspace, stop_codex_review_for_workspace
from core.decorators import with_workspace
from core.global_flags import is_codex_enabled
from core.helpers import compute_phase_sequence
from core.i18n import t
from core.terminal import notify_workspace
from services import plan_service
from services import progress_service
from services import research_service
from services import scope_service

def _group_comments(comments):
    """Group a flat list of comment dicts by 'scope:target' key."""
    grouped = {}
    for comment in comments:
        key = f"{comment['scope']}:{comment['target'] or ''}"
        grouped.setdefault(key, []).append(comment)
    return grouped


# Phases that have sub-phases — bare number normalizes to .0
_PHASES_WITH_SUBS = {"1", "2", "3", "4"}

# All valid phase patterns
_VALID_PHASE_RE = re.compile(
    r'^(0|1\.[0-4]|2\.[01]|3\.\d+\.[0-4]|4\.[0-2]|5)$'
)


def normalize_phase(phase):
    """Normalize and validate a phase string. Returns normalized phase or None if invalid."""
    phase = phase.strip()
    if phase in _PHASES_WITH_SUBS:
        phase = phase + ".0"
    if not _VALID_PHASE_RE.match(phase):
        return None
    return phase

bp = Blueprint("state", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/state", methods=["GET"])
@with_workspace
def get_workspace_state(db, ws, project):
    comments = _group_comments(comment_service.get_comments(db, ws["id"]))

    scope = plan_service.get_scope(ws)
    plan = plan_service.get_plan(ws)
    phase_sequence = compute_phase_sequence(plan)

    history_rows = db.execute(
        "SELECT from_phase, to_phase, time FROM phase_history WHERE workspace_id = ? ORDER BY id",
        (ws["id"],)
    ).fetchall()
    history = [{"from": row["from_phase"], "to": row["to_phase"], "time": row["time"]} for row in history_rows]

    session_rows = db.execute(
        "SELECT session_id, started_at FROM session_history "
        "WHERE workspace_id = ? ORDER BY id DESC",
        (ws["id"],)
    ).fetchall()
    sessions = [{"session_id": r["session_id"], "started_at": r["started_at"]} for r in session_rows]

    all_ids = [e["id"] for e in research_service.list_research(db, ws["id"])]
    research = research_service.get_research(db, ws["id"], all_ids)

    discussions = discussion_service.list_discussions(db, ws["id"])

    progress = progress_service.get_progress(db, ws["id"])

    impact_analysis = None
    if "impact_analysis_json" in ws.keys() and ws["impact_analysis_json"]:
        try:
            impact_analysis = json.loads(ws["impact_analysis_json"])
        except json.JSONDecodeError:
            pass

    return jsonify({
        "phase": ws["phase"],
        "status": ws["status"],
        "scope": scope,
        "scope_status": ws["scope_status"],
        "plan": plan,
        "plan_status": ws["plan_status"],
        "prev_plan_status": ws["prev_plan_status"],
        "has_prev_plan": ws["prev_plan_json"] is not None and ws["prev_plan_json"] != "",
        "phase_sequence": phase_sequence,
        "locale": ws["locale"],
        "session_id": ws["session_id"],
        "working_dir": ws["working_dir"],
        "branch": ws["branch"],
        "claude_command": ws["claude_command"] or "claude",
        "skip_permissions": bool(ws["skip_permissions"]),
        "restrict_to_workspace": bool(ws_field(ws, "restrict_to_workspace", 1)),
        "allowed_external_paths": ws_field(ws, "allowed_external_paths", "/tmp/"),
        "comments": comments,
        "research": research,
        "discussions": discussions,
        "phaseHistory": history,
        "progress": progress,
        "sessions": sessions,
        "impact_analysis": impact_analysis,
        "yolo_mode": bool(ws_field(ws, "yolo_mode", 0)),
        "codex_globally_enabled": is_codex_enabled(db, default=False),
        "codex_phase1_globally_enabled": is_codex_enabled(db, default=False),
        "codex_review_enabled": bool(ws_field(ws, "codex_review_enabled", 0)),
        "codex_review_status": ws_field(ws, "codex_review_status", "idle"),
        "codex_review_last_error": ws_field(ws, "codex_review_last_error", ""),
    })


@bp.route("/api/ws/<project_id>/<path:branch>/locale", methods=["PUT"])
@with_workspace
def set_locale(db, ws, project):
    body = request.get_json(silent=True) or {}
    locale = body.get("locale", "en").strip()
    if locale not in ("en", "ru"):
        return jsonify({"error": t("api.error.unsupportedLocale")}), 400
    db.execute("UPDATE workspaces SET locale = ? WHERE id = ?", (locale, ws["id"]))
    db.commit()
    return jsonify({"ok": True, "locale": locale})


@bp.route("/api/ws/<project_id>/<path:branch>/yolo", methods=["PUT"])
@with_workspace
def set_yolo_mode(db, ws, project):
    body = request.get_json(silent=True) or {}
    enabled = 1 if body.get("enabled") else 0
    db.execute("UPDATE workspaces SET yolo_mode = ? WHERE id = ?", (enabled, ws["id"]))
    db.commit()
    return jsonify({"ok": True, "yolo_mode": bool(enabled)})


@bp.route("/api/ws/<project_id>/<path:branch>/codex-review", methods=["PUT"])
@with_workspace
def set_codex_review(db, ws, project):
    body = request.get_json(silent=True) or {}
    enabled = 1 if body.get("enabled") else 0

    if enabled and not is_codex_enabled(db, default=False):
        return jsonify({"error": "Codex is disabled in global setup"}), 409

    db.execute("UPDATE workspaces SET codex_review_enabled = ? WHERE id = ?", (enabled, ws["id"]))
    db.commit()

    if enabled:
        maybe_start_codex_review_for_workspace(ws["id"])
    else:
        stop_codex_review_for_workspace(ws["id"], reset_state=True)

    with get_db_ctx() as fresh_db:
        fresh = fresh_db.execute("SELECT * FROM workspaces WHERE id = ?", (ws["id"],)).fetchone()
    return jsonify({
        "ok": True,
        "codex_review_enabled": bool(ws_field(fresh, "codex_review_enabled", 0)),
        "codex_review_status": ws_field(fresh, "codex_review_status", "idle"),
        "codex_review_last_error": ws_field(fresh, "codex_review_last_error", ""),
    })


@bp.route("/api/ws/<project_id>/<path:branch>/scope", methods=["PUT"])
@with_workspace
def set_scope(db, ws, project):
    """Update workspace scope as a phase-keyed map."""
    body = request.get_json(silent=True) or {}
    scope = body.get("scope", {})

    result = scope_service.set_scope(db, ws, scope, enforce_phase_guard=False)
    if "error" in result:
        return jsonify(result), 400
    db.commit()
    return jsonify({"ok": True, "scope": scope})


@bp.route("/api/ws/<project_id>/<path:branch>/scope-status", methods=["POST"])
@with_workspace
def set_scope_status(db, ws, project):
    """Set scope status: pending, approved, or rejected."""
    body = request.get_json(silent=True) or {}
    status = body.get("status", "pending")
    result = scope_service.set_scope_status(db, ws["id"], status, locale=ws["locale"])
    if "error" in result:
        return jsonify(result), 400
    db.commit()

    if status == 'approved':
        notify_workspace(ws, 'Scope has been approved.')
    elif status == 'rejected':
        notify_workspace(ws, 'Scope has been rejected. Check comments for feedback.')

    return jsonify({"ok": True, "scope_status": status})


@bp.route("/api/ws/<project_id>/<path:branch>/plan-status", methods=["POST"])
@with_workspace
def set_plan_status(db, ws, project):
    """Set plan status: pending, approved, or rejected."""
    body = request.get_json(silent=True) or {}
    status = body.get("status", "pending")
    if status not in ("pending", "approved", "rejected"):
        return jsonify({"error": t("api.error.invalidStatus")}), 400
    db.execute("UPDATE workspaces SET plan_status = ? WHERE id = ?", (status, ws["id"]))
    db.commit()

    if status == 'approved':
        notify_workspace(ws, 'Plan has been approved.')
    elif status == 'rejected':
        notify_workspace(ws, 'Plan has been rejected. Check comments for feedback.')

    return jsonify({"ok": True, "plan_status": status})


@bp.route("/api/ws/<project_id>/<path:branch>/phase", methods=["PUT"])
@with_workspace
def set_phase(db, ws, project):
    body = request.json or {}
    new_phase = body.get("phase", "").strip()
    if not new_phase:
        return jsonify({"error": t("api.error.phaseRequired")}), 400

    new_phase = normalize_phase(new_phase)
    if new_phase is None:
        return jsonify({"error": t("api.error.invalidPhase")}), 400

    old_phase = ws["phase"]
    db.execute("UPDATE workspaces SET phase = ? WHERE id = ?", (new_phase, ws["id"]))
    db.execute(
        "INSERT INTO phase_history (workspace_id, from_phase, to_phase, time) VALUES (?, ?, ?, ?)",
        (ws["id"], old_phase, new_phase, datetime.now().isoformat())
    )

    from advance.orchestrator import is_user_gate

    if is_user_gate(new_phase):
        import secrets
        nonce = secrets.token_urlsafe(32)
        db.execute("UPDATE workspaces SET gate_nonce = ? WHERE id = ?", (nonce, ws["id"]))

    db.commit()
    if new_phase == "4.0":
        maybe_start_codex_review_for_workspace(ws["id"])
    elif old_phase == "4.0" and ws_field(ws, "codex_review_status", "idle") == "running":
        stop_codex_review_for_workspace(ws["id"], reset_state=True)
    return jsonify({"phase": new_phase, "previous_phase": old_phase})


@bp.route("/api/ws/<project_id>/<path:branch>/gate-nonce", methods=["GET"])
@with_workspace
def get_gate_nonce(db, ws, project):
    nonce = ws["gate_nonce"] if ws["gate_nonce"] else None
    return jsonify({"nonce": nonce})


@bp.route("/api/progress", methods=["GET"])
def query_progress():
    """Query progress entries by date range. For daily reflection.

    Query params:
        date: single date (YYYY-MM-DD) -- returns entries created/updated on that day
        from: start date (YYYY-MM-DD)
        to: end date (YYYY-MM-DD)
        project_id: optional filter by project
    """
    date = request.args.get("date")
    date_from = request.args.get("from", date)
    date_to = request.args.get("to", date)
    project_id = request.args.get("project_id")

    if not date_from or not date_to:
        return jsonify({"error": t("api.error.provideDateParams")}), 400

    query = (
        "SELECT pe.phase, pe.summary, pe.details_json, pe.created_at, pe.updated_at, "
        "w.branch, w.working_dir, p.name AS project_name, p.id AS project_id "
        "FROM progress_entries pe "
        "JOIN workspaces w ON pe.workspace_id = w.id "
        "JOIN projects p ON w.project_id = p.id "
        "WHERE (pe.created_at >= ? OR pe.updated_at >= ?) "
        "AND (pe.created_at < ? OR pe.updated_at < ?) "
    )
    start = f"{date_from}T00:00:00"
    end = f"{date_to}T23:59:59"
    params = [start, start, end, end]

    if project_id:
        query += "AND p.id = ? "
        params.append(project_id)

    query += "ORDER BY pe.updated_at"

    with get_db_ctx() as db:
        rows = db.execute(query, params).fetchall()

    entries = []
    for row in rows:
        entry = {
            "project": row["project_name"],
            "project_id": row["project_id"],
            "branch": row["branch"],
            "phase": row["phase"],
            "summary": row["summary"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if row["details_json"]:
            try:
                entry["details"] = json.loads(row["details_json"])
            except json.JSONDecodeError:
                pass
        entries.append(entry)

    return jsonify({"entries": entries, "date_from": date_from, "date_to": date_to})


@bp.route("/api/ws/<project_id>/<path:branch>/restore-plan", methods=["POST"])
@with_workspace
def restore_plan(db, ws, project):
    """Restore previous plan version. User can always restore (no approval guard)."""
    if not ws["prev_plan_json"]:
        return jsonify({"error": t("api.error.noPreviousPlan")}), 404

    new_ws = plan_service.restore_plan(db, ws)
    db.commit()
    return jsonify({"ok": True, "phase": new_ws["phase"]})


@bp.route("/api/ws/<project_id>/<path:branch>/research/<int:research_id>/prove", methods=["POST"])
@with_workspace
def toggle_research_proven(db, ws, project, research_id):
    """Toggle research entry proven status. Body: {"proven": true/false}"""
    body = request.get_json(silent=True) or {}
    proven = body.get("proven", False)

    result = research_service.set_proven(
        db, research_id, ws["id"], proven,
        notes="Manual override via admin panel",
    )
    if "error" in result:
        return jsonify({"error": t("api.error.researchEntryNotFound")}), 404

    db.commit()
    return jsonify(result)


@bp.route("/api/ws/<project_id>/<path:branch>/can-modify", methods=["POST"])
@with_workspace
def can_modify(db, ws, project):
    """Check if a file can be modified in the current workspace state.

    Called by pre-tool hook to enforce scope and approval.
    Body: {"file": "relative/path/to/file"}

    Checks (in order):
    1. Files inside .claude/ are ALWAYS allowed (workspace metadata, memory, etc.)
    2. Plan must be approved (if plan exists with execution items)
    3. Scope must be approved
    4. File must match scope patterns (must or may)

    Returns: {"allowed": true} or {"allowed": false, "reason": "..."}
    """
    body = request.get_json(silent=True) or {}
    file_path = body.get("file", "").strip()
    if not file_path:
        return jsonify({"error": t("api.error.fileParameterRequired")}), 400

    locale = ws["locale"] if ws["locale"] else "en"

    # .claude/ files are always writable (workspace metadata, memory, configs)
    if file_path.startswith(".claude/") or file_path.startswith(".claude\\"):
        return jsonify({"allowed": True, "reason": t("api.scope.workspaceMetadataAlwaysWritable", locale)})

    # Check plan approval (if plan exists with execution items)
    plan = plan_service.get_plan(ws)
    if plan.get("execution"):
        plan_status = ws_field(ws, "plan_status", "pending")
        if plan_status != "approved":
            return jsonify({"allowed": False, "reason": t("api.scope.planNotApproved", locale)})

    # Check scope approval
    scope_status = ws_field(ws, "scope_status", "pending")
    if scope_status != "approved":
        return jsonify({"allowed": False, "reason": t("api.scope.scopeNotApproved", locale)})

    # Check file matches scope patterns
    scope_map = plan_service.get_scope(ws)
    phase = ws["phase"]

    must_patterns, may_patterns = scope_service.get_scope_patterns(scope_map, phase)
    if not must_patterns and not may_patterns:
        # No scope patterns defined -- allow (scope is approved but empty means no restrictions)
        return jsonify({"allowed": True, "reason": t("api.scope.noScopePatternsDefinied", locale)})

    if scope_service.match_scope_patterns(file_path, scope_map, phase):
        return jsonify({"allowed": True, "reason": t("api.scope.matchesScopePattern", locale, pattern=file_path)})

    return jsonify({"allowed": False, "reason": t("api.scope.fileOutsideApprovedScope", locale, file_path=file_path)})


@bp.route("/api/ws/<project_id>/<path:branch>/research/<int:research_id>", methods=["DELETE"])
@with_workspace
def delete_research(db, ws, project, research_id):
    deleted = research_service.delete_research(db, research_id, ws["id"])

    if not deleted:
        return jsonify({"error": t("api.error.researchEntryNotFound")}), 404

    db.commit()
    return jsonify({"ok": True})
