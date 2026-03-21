"""Scope domain logic: set, validate status, and pattern matching for workspace scope.

All scope business logic lives here. MCP tools and route handlers are thin
wrappers that delegate to this module.
"""
import json
import re

from helpers import match_scope_pattern
from i18n import t
from phase import Phase

_PHASE_3_SUB_RE = re.compile(r'^3\.\d+\.\d+$')

VALID_SCOPE_STATUSES = ("pending", "approved", "rejected")


def set_scope(db, ws, scope_data, enforce_phase_guard=True):
    """Update scope_json and reset scope_status to 'pending'.

    When enforce_phase_guard=True (default, used by MCP), rejects updates at phase 0.
    When enforce_phase_guard=False (used by admin UI), allows updates at any phase.
    Always resets approval so the user must re-approve.
    Returns a result dict with ok/error keys.
    """
    locale = ws["locale"] or "en"
    phase = ws["phase"]

    if enforce_phase_guard and Phase(phase) < "1.0":
        return {"error": t("mcp.error.scopePhase0", locale)}

    scope_json = json.dumps(scope_data)
    db.execute("UPDATE workspaces SET scope_json = ? WHERE id = ?", (scope_json, ws["id"]))
    db.execute("UPDATE workspaces SET scope_status = 'pending' WHERE id = ?", (ws["id"],))

    return {"ok": True, "phase": phase, "scope_status": "pending",
            "note": t("mcp.error.scopeNoteRevoked", locale)}


def set_scope_status(db, ws_id, status):
    """Validate and UPDATE scope_status for the given workspace.

    Returns a result dict with ok/error keys.
    """
    if status not in VALID_SCOPE_STATUSES:
        return {"error": t("api.error.invalidStatus")}

    db.execute("UPDATE workspaces SET scope_status = ? WHERE id = ?", (status, ws_id))
    return {"ok": True, "scope_status": status}


def get_scope_patterns(scope, phase):
    """Return (must_patterns, may_patterns) for the given phase from a parsed scope map.

    For 3.N.K phases: uses the 3.N sub-key only.
    For all other phases: aggregates across all phase entries in the scope map.

    Args:
        scope: parsed scope dict (phase-keyed map from scope_json)
        phase: current phase string e.g. "3.1.0", "2.0"

    Returns:
        tuple of (must_patterns list, may_patterns list)
    """
    if _PHASE_3_SUB_RE.match(phase):
        parts = phase.split(".")
        sub_key = parts[0] + "." + parts[1]
        phase_scope = scope.get(sub_key, {})
        return phase_scope.get("must", []), phase_scope.get("may", [])

    must_patterns = []
    may_patterns = []
    for ps in scope.values():
        if isinstance(ps, dict):
            must_patterns.extend(ps.get("must", []))
            may_patterns.extend(ps.get("may", []))
    return must_patterns, may_patterns


def get_phase_must_patterns(scope, phase):
    """Return only 'must' patterns for the current sub-phase.

    Always scopes to the specific 3.N sub-key, never aggregates.
    Used by advance validation which needs per-sub-phase must coverage.

    Args:
        scope: parsed scope dict
        phase: current phase string e.g. "3.1.0"

    Returns:
        list of must pattern strings
    """
    parts = phase.split(".")
    sub_key = parts[0] + "." + parts[1] if len(parts) >= 2 else phase
    phase_scope = scope.get(sub_key, {})
    return phase_scope.get("must", [])


def match_scope_patterns(file_path, scope, phase):
    """Check if a relative file path matches any must or may scope pattern for the phase.

    Args:
        file_path: relative file path (e.g. "src/main.py")
        scope: parsed scope dict (phase-keyed map)
        phase: current phase string

    Returns:
        True if the file matches at least one pattern, False otherwise.
    """
    must_patterns, may_patterns = get_scope_patterns(scope, phase)
    all_patterns = must_patterns + may_patterns

    if not all_patterns:
        return True

    for pattern in all_patterns:
        match_pattern = pattern.rstrip("/") + "/**" if pattern.endswith("/") else pattern
        if match_scope_pattern(file_path, match_pattern):
            return True
    return False
