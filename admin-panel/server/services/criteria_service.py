"""Acceptance criteria CRUD domain logic: propose, get, update, set status, validate, delete.

All criteria business logic lives here. MCP tools and route handlers are thin
wrappers that delegate to this module.

Automated validation (file-based checks) lives in criteria_validators.py.
This module handles the data operations.
"""
import json
from datetime import datetime

from core.helpers import VALID_CRITERIA_TYPES


def _safe_parse_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _format_criterion(row):
    """Build a criterion dict from a DB row."""
    return {
        "id": row["id"],
        "type": row["type"],
        "description": row["description"],
        "details": _safe_parse_json(row["details_json"]),
        "source": row["source"],
        "status": row["status"],
        "validated": row["validated"],
        "validation_message": row["validation_message"],
    }


def _validate_details_json(details_json, criterion_type):
    """Parse and validate details_json string. Returns (parsed_or_None, error_or_None, warnings)."""
    warnings = []
    if not details_json:
        return None, None, warnings

    try:
        parsed = json.loads(details_json)
    except json.JSONDecodeError as e:
        return None, f"details_json is not valid JSON: {e}", warnings

    if not isinstance(parsed, dict):
        return None, f"details_json must be a JSON object, got {type(parsed).__name__}", warnings

    if criterion_type in ("unit_test", "integration_test") and "file" not in parsed:
        warnings.append("details_json is missing recommended 'file' key for unit_test/integration_test")
    if criterion_type == "bdd_scenario" and "file" not in parsed:
        warnings.append("details_json is missing recommended 'file' key for bdd_scenario")

    return parsed, None, warnings


def propose_criterion(db, workspace_id, criterion_type, description, details_json=None, source="agent"):
    """Insert a new acceptance criterion in 'proposed' status.

    Returns a result dict with ok/criterion or error key.
    """
    if criterion_type not in VALID_CRITERIA_TYPES:
        return {"error": f"Invalid criteria type '{criterion_type}'. Valid: {', '.join(VALID_CRITERIA_TYPES)}"}

    _, error, warnings = _validate_details_json(details_json, criterion_type)
    if error:
        return {"error": error}

    cursor = db.execute(
        "INSERT INTO acceptance_criteria "
        "(workspace_id, type, description, details_json, source, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'proposed', ?)",
        (workspace_id, criterion_type, description, details_json or None, source, datetime.now().isoformat())
    )
    criterion_id = cursor.lastrowid

    row = db.execute(
        "SELECT id, type, description, details_json, source, status, validated, validation_message "
        "FROM acceptance_criteria WHERE id = ?",
        (criterion_id,)
    ).fetchone()

    result = {"ok": True, "criterion": _format_criterion(row)}
    if warnings:
        result["warnings"] = warnings
    return result


def get_criteria(db, workspace_id, status=None, criterion_type=None):
    """Get acceptance criteria for a workspace with optional filters.

    Returns a list of criterion dicts.
    """
    query = (
        "SELECT id, type, description, details_json, source, status, validated, validation_message "
        "FROM acceptance_criteria WHERE workspace_id = ?"
    )
    params = [workspace_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    if criterion_type:
        query += " AND type = ?"
        params.append(criterion_type)
    query += " ORDER BY id"

    rows = db.execute(query, params).fetchall()
    return [_format_criterion(row) for row in rows]


def update_criterion(db, criterion_id, workspace_id, description=None, details_json=None):
    """Update description and/or details of an existing criterion.

    Blocks updates to accepted criteria. Resets rejected criteria back to proposed.
    Returns a result dict with ok/criterion or error key.
    """
    row = db.execute(
        "SELECT * FROM acceptance_criteria WHERE id = ? AND workspace_id = ?",
        (criterion_id, workspace_id)
    ).fetchone()
    if not row:
        return {"error": "criterion_not_found"}

    if row["status"] == "accepted":
        return {"error": "cannot_update_accepted"}

    reset_status = row["status"] == "rejected"

    _, error, warnings = _validate_details_json(details_json, row["type"])
    if error:
        return {"error": error}

    updates = []
    params = []
    if description:
        updates.append("description = ?")
        params.append(description)
    if details_json:
        updates.append("details_json = ?")
        params.append(details_json)

    if not updates:
        return {"error": "nothing_to_update"}

    params.append(criterion_id)
    db.execute(
        f"UPDATE acceptance_criteria SET {', '.join(updates)} WHERE id = ?",
        params
    )

    if reset_status:
        db.execute("UPDATE acceptance_criteria SET status = 'proposed' WHERE id = ?", (criterion_id,))

    updated = db.execute(
        "SELECT id, type, description, details_json, source, status, validated, validation_message "
        "FROM acceptance_criteria WHERE id = ?",
        (criterion_id,)
    ).fetchone()

    result = {"ok": True, "id": criterion_id}
    if reset_status:
        result["status_reset"] = "proposed"
    if warnings:
        result["warnings"] = warnings
    result["criterion"] = _format_criterion(updated)
    return result


def set_criterion_status(db, criterion_id, workspace_id, status):
    """Set the status of a criterion (accepted/rejected).

    Returns a result dict with ok or error key.
    """
    row = db.execute(
        "SELECT id FROM acceptance_criteria WHERE id = ? AND workspace_id = ?",
        (criterion_id, workspace_id)
    ).fetchone()
    if not row:
        return {"error": "criterion_not_found"}

    db.execute(
        "UPDATE acceptance_criteria SET status = ? WHERE id = ?",
        (status, criterion_id)
    )
    return {"ok": True}


def validate_criterion_manual(db, criterion_id, workspace_id, passed, message=None):
    """Manually validate a custom criterion (pass or fail).

    Only works for criteria with type='custom'.
    Returns a result dict with ok or error key.
    """
    row = db.execute(
        "SELECT id, type FROM acceptance_criteria WHERE id = ? AND workspace_id = ?",
        (criterion_id, workspace_id)
    ).fetchone()
    if not row:
        return {"error": "criterion_not_found"}

    if row["type"] != "custom":
        return {"error": "only_custom_criteria"}

    validated = 1 if passed else -1
    db.execute(
        "UPDATE acceptance_criteria SET validated = ?, validation_message = ? WHERE id = ?",
        (validated, message, criterion_id)
    )
    return {"ok": True}


def delete_criterion(db, criterion_id, workspace_id):
    """Delete a criterion by ID.

    Returns a result dict with ok or error key.
    """
    rows = db.execute(
        "DELETE FROM acceptance_criteria WHERE id = ? AND workspace_id = ?",
        (criterion_id, workspace_id)
    ).rowcount

    if rows == 0:
        return {"error": "criterion_not_found"}
    return {"ok": True}
