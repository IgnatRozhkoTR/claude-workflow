"""Workspace state routes: phase, scope, plan, progress."""
import json
import re
from datetime import datetime

from flask import Blueprint, jsonify, request

from db import get_db
from helpers import compute_phase_sequence, find_workspace, get_comments_for_workspace
from i18n import t
from terminal import session_name, session_exists, send_keys

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
def get_workspace_state(project_id, branch):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        comments = get_comments_for_workspace(db, ws["id"])

        scope = json.loads(ws["scope_json"]) if ws["scope_json"] else {}
        plan = json.loads(ws["plan_json"]) if ws["plan_json"] else {"description": "", "systemDiagram": "", "execution": []}
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

        research_rows = db.execute(
            "SELECT id, topic, summary, findings_json, proven, discussion_id, created_at "
            "FROM research_entries WHERE workspace_id = ? ORDER BY id",
            (ws["id"],)
        ).fetchall()
        research = []
        for row in research_rows:
            try:
                findings = json.loads(row["findings_json"])
            except json.JSONDecodeError:
                findings = []
            research.append({
                "id": row["id"],
                "topic": row["topic"],
                "summary": row["summary"],
                "findings": findings,
                "proven": row["proven"],
                "discussion_id": row["discussion_id"],
                "created_at": row["created_at"],
            })

        discussion_rows = db.execute(
            "SELECT id, parent_id, text, author, status, type, hidden, created_at, resolved_at "
            "FROM discussions WHERE workspace_id = ? AND scope IS NULL AND parent_id IS NULL ORDER BY id",
            (ws["id"],)
        ).fetchall()
        discussions = []
        for row in discussion_rows:
            d = dict(row)
            replies = db.execute(
                "SELECT id, text, author, status, created_at, resolved_at "
                "FROM discussions WHERE parent_id = ? ORDER BY id",
                (row["id"],)
            ).fetchall()
            d["replies"] = [dict(r) for r in replies]
            discussions.append(d)

        progress_rows = db.execute(
            "SELECT phase, summary, details_json, created_at, updated_at "
            "FROM progress_entries WHERE workspace_id = ? ORDER BY id",
            (ws["id"],)
        ).fetchall()
        progress = {}
        for row in progress_rows:
            entry = {"summary": row["summary"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
            if row["details_json"]:
                try:
                    entry["details"] = json.loads(row["details_json"])
                except json.JSONDecodeError:
                    pass
            progress[row["phase"]] = entry

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
            "comments": comments,
            "research": research,
            "discussions": discussions,
            "phaseHistory": history,
            "progress": progress,
            "sessions": sessions,
        })
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/locale", methods=["PUT"])
def set_locale(project_id, branch):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404
        body = request.get_json(silent=True) or {}
        locale = body.get("locale", "en").strip()
        if locale not in ("en", "ru"):
            return jsonify({"error": t("api.error.unsupportedLocale")}), 400
        db.execute("UPDATE workspaces SET locale = ? WHERE id = ?", (locale, ws["id"]))
        db.commit()
        return jsonify({"ok": True, "locale": locale})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/scope", methods=["PUT"])
def set_scope(project_id, branch):
    """Update workspace scope as a phase-keyed map."""
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        body = request.get_json(silent=True) or {}
        scope = body.get("scope", {})
        scope_json = json.dumps(scope)

        db.execute("UPDATE workspaces SET scope_json = ? WHERE id = ?", (scope_json, ws["id"]))

        db.commit()
        return jsonify({"ok": True, "scope": scope})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/scope-status", methods=["POST"])
def set_scope_status(project_id, branch):
    """Set scope status: pending, approved, or rejected."""
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        body = request.get_json(silent=True) or {}
        status = body.get("status", "pending")
        if status not in ("pending", "approved", "rejected"):
            return jsonify({"error": t("api.error.invalidStatus")}), 400

        db.execute("UPDATE workspaces SET scope_status = ? WHERE id = ?", (status, ws["id"]))
        db.commit()

        if status in ('approved', 'rejected'):
            try:
                tmux_name = session_name(project_id, branch)
                if session_exists(tmux_name):
                    if status == 'approved':
                        send_keys(tmux_name, 'Scope has been approved.')
                    else:
                        send_keys(tmux_name, 'Scope has been rejected. Check comments for feedback.')
            except Exception:
                pass

        return jsonify({"ok": True, "scope_status": status})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/plan-status", methods=["POST"])
def set_plan_status(project_id, branch):
    """Set plan status: pending, approved, or rejected."""
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404
        body = request.get_json(silent=True) or {}
        status = body.get("status", "pending")
        if status not in ("pending", "approved", "rejected"):
            return jsonify({"error": t("api.error.invalidStatus")}), 400
        db.execute("UPDATE workspaces SET plan_status = ? WHERE id = ?", (status, ws["id"]))
        db.commit()

        if status in ('approved', 'rejected'):
            try:
                tmux_name = session_name(project_id, branch)
                if session_exists(tmux_name):
                    if status == 'approved':
                        send_keys(tmux_name, 'Plan has been approved.')
                    else:
                        send_keys(tmux_name, 'Plan has been rejected. Check comments for feedback.')
            except Exception:
                pass

        return jsonify({"ok": True, "plan_status": status})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/phase", methods=["PUT"])
def set_phase(project_id, branch):
    body = request.json or {}
    new_phase = body.get("phase", "").strip()
    if not new_phase:
        return jsonify({"error": t("api.error.phaseRequired")}), 400

    new_phase = normalize_phase(new_phase)
    if new_phase is None:
        return jsonify({"error": t("api.error.invalidPhase")}), 400

    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        old_phase = ws["phase"]
        db.execute("UPDATE workspaces SET phase = ? WHERE id = ?", (new_phase, ws["id"]))
        db.execute(
            "INSERT INTO phase_history (workspace_id, from_phase, to_phase, time) VALUES (?, ?, ?, ?)",
            (ws["id"], old_phase, new_phase, datetime.now().isoformat())
        )

        from advance_service import is_user_gate

        if is_user_gate(new_phase):
            import secrets
            nonce = secrets.token_urlsafe(32)
            db.execute("UPDATE workspaces SET gate_nonce = ? WHERE id = ?", (nonce, ws["id"]))

        db.commit()
        return jsonify({"phase": new_phase, "previous_phase": old_phase})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/gate-nonce", methods=["GET"])
def get_gate_nonce(project_id, branch):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        nonce = ws["gate_nonce"] if ws["gate_nonce"] else None
        return jsonify({"nonce": nonce})
    finally:
        db.close()


@bp.route("/api/progress", methods=["GET"])
def query_progress():
    """Query progress entries by date range. For daily reflection.

    Query params:
        date: single date (YYYY-MM-DD) — returns entries created/updated on that day
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

    db = get_db()
    try:
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
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/restore-plan", methods=["POST"])
def restore_plan(project_id, branch):
    """Restore previous plan version. User can always restore (no approval guard)."""
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        if not ws["prev_plan_json"]:
            return jsonify({"error": t("api.error.noPreviousPlan")}), 404

        # Swap current and prev (SQLite evaluates all RHS from original row before updating)
        db.execute("""
            UPDATE workspaces SET
                plan_json = prev_plan_json,
                scope_json = prev_scope_json,
                phase = prev_phase,
                plan_status = prev_plan_status,
                scope_status = prev_scope_status,
                prev_plan_json = plan_json,
                prev_scope_json = scope_json,
                prev_phase = phase,
                prev_plan_status = plan_status,
                prev_scope_status = scope_status
            WHERE id = ?
        """, (ws["id"],))

        # Record phase history if phase changed
        new_ws = db.execute("SELECT phase FROM workspaces WHERE id = ?", (ws["id"],)).fetchone()
        if new_ws["phase"] != ws["phase"]:
            db.execute(
                "INSERT INTO phase_history (workspace_id, from_phase, to_phase, time) VALUES (?, ?, ?, ?)",
                (ws["id"], ws["phase"], new_ws["phase"], datetime.now().isoformat())
            )

        db.commit()
        return jsonify({"ok": True, "phase": new_ws["phase"]})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/research/<int:research_id>/prove", methods=["POST"])
def toggle_research_proven(project_id, branch, research_id):
    """Toggle research entry proven status. Body: {"proven": true/false}"""
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        row = db.execute(
            "SELECT id FROM research_entries WHERE id = ? AND workspace_id = ?",
            (research_id, ws["id"])
        ).fetchone()
        if not row:
            return jsonify({"error": t("api.error.researchEntryNotFound")}), 404

        body = request.get_json(silent=True) or {}
        proven_val = 1 if body.get("proven", False) else -1

        db.execute(
            "UPDATE research_entries SET proven = ?, proven_notes = ? WHERE id = ?",
            (proven_val, "Manual override via admin panel", research_id)
        )
        db.commit()
        return jsonify({"ok": True, "id": research_id, "proven": proven_val})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/can-modify", methods=["POST"])
def can_modify(project_id, branch):
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
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"allowed": False, "reason": t("api.error.workspaceNotFound")}), 404

        body = request.get_json(silent=True) or {}
        file_path = body.get("file", "").strip()
        if not file_path:
            return jsonify({"error": t("api.error.fileParameterRequired")}), 400

        locale = ws["locale"] if ws["locale"] else "en"

        # .claude/ files are always writable (workspace metadata, memory, configs)
        if file_path.startswith(".claude/") or file_path.startswith(".claude\\"):
            return jsonify({"allowed": True, "reason": t("api.scope.workspaceMetadataAlwaysWritable", locale)})

        # Check plan approval (if plan exists with execution items)
        plan = json.loads(ws["plan_json"]) if ws["plan_json"] else {}
        if plan.get("execution"):
            plan_status = ws["plan_status"] if "plan_status" in ws.keys() else "pending"
            if plan_status != "approved":
                return jsonify({"allowed": False, "reason": t("api.scope.planNotApproved", locale)})

        # Check scope approval
        scope_status = ws["scope_status"] if "scope_status" in ws.keys() else "pending"
        if scope_status != "approved":
            return jsonify({"allowed": False, "reason": t("api.scope.scopeNotApproved", locale)})

        # Check file matches scope patterns
        scope_map = json.loads(ws["scope_json"]) if ws["scope_json"] else {}
        phase = ws["phase"]
        parts = phase.split(".")
        sub_key = parts[0] + "." + parts[1] if len(parts) >= 2 else phase

        if phase.startswith("3.") and len(parts) >= 3:
            phase_scope = scope_map.get(sub_key, {})
            must_patterns = phase_scope.get("must", [])
            may_patterns = phase_scope.get("may", [])
        else:
            must_patterns = []
            may_patterns = []
            for ps in scope_map.values():
                must_patterns.extend(ps.get("must", []))
                may_patterns.extend(ps.get("may", []))
        all_patterns = must_patterns + may_patterns

        if not all_patterns:
            # No scope patterns defined — allow (scope is approved but empty means no restrictions)
            return jsonify({"allowed": True, "reason": t("api.scope.noScopePatternsDefinied", locale)})

        from helpers import match_scope_pattern

        for pattern in all_patterns:
            if pattern.endswith("/"):
                match_pattern = pattern.rstrip("/") + "/**"
            else:
                match_pattern = pattern
            if match_scope_pattern(file_path, match_pattern):
                return jsonify({"allowed": True, "reason": t("api.scope.matchesScopePattern", locale, pattern=pattern)})

        return jsonify({"allowed": False, "reason": t("api.scope.fileOutsideApprovedScope", locale, file_path=file_path)})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/research/<int:research_id>", methods=["DELETE"])
def delete_research(project_id, branch, research_id):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        rows = db.execute(
            "DELETE FROM research_entries WHERE id = ? AND workspace_id = ?",
            (research_id, ws["id"])
        ).rowcount
        db.commit()

        if rows == 0:
            return jsonify({"error": t("api.error.researchEntryNotFound")}), 404

        return jsonify({"ok": True})
    finally:
        db.close()
