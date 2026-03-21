"""Acceptance criteria routes: CRUD and manual validation."""
import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from db import get_db
from helpers import find_workspace, VALID_CRITERIA_TYPES
from i18n import t

bp = Blueprint("criteria", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/criteria", methods=["GET"])
def get_criteria(project_id, branch):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        query = (
            "SELECT id, type, description, details_json, source, status, validated, validation_message "
            "FROM acceptance_criteria WHERE workspace_id = ?"
        )
        params = [ws["id"]]
        status_filter = request.args.get("status")
        type_filter = request.args.get("type")
        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)
        if type_filter:
            query += " AND type = ?"
            params.append(type_filter)
        query += " ORDER BY id"

        rows = db.execute(query, params).fetchall()
        criteria = [
            {
                "id": row["id"],
                "type": row["type"],
                "description": row["description"],
                "details": json.loads(row["details_json"]) if row["details_json"] else None,
                "source": row["source"],
                "status": row["status"],
                "validated": row["validated"],
                "validation_message": row["validation_message"],
            }
            for row in rows
        ]
        return jsonify({"criteria": criteria})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/criteria", methods=["POST"])
def create_criterion(project_id, branch):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        body = request.get_json(silent=True) or {}
        criterion_type = body.get("type")
        description = body.get("description")

        if not criterion_type:
            return jsonify({"error": t("api.error.typeRequired")}), 400
        if criterion_type not in VALID_CRITERIA_TYPES:
            return jsonify({"error": t("api.error.invalidCriteriaType", valid_types=", ".join(VALID_CRITERIA_TYPES))}), 400
        if not description:
            return jsonify({"error": t("api.error.descriptionRequired")}), 400

        cursor = db.execute(
            "INSERT INTO acceptance_criteria "
            "(workspace_id, type, description, details_json, source, status, created_at) "
            "VALUES (?, ?, ?, ?, 'user', 'proposed', ?)",
            (ws["id"], criterion_type, description, body.get("details_json"),
             datetime.now().isoformat())
        )
        db.commit()
        return jsonify({"ok": True, "id": cursor.lastrowid}), 201
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/criteria/<int:criterion_id>", methods=["PUT"])
def update_criterion(project_id, branch, criterion_id):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        row = db.execute(
            "SELECT id FROM acceptance_criteria WHERE id = ? AND workspace_id = ?",
            (criterion_id, ws["id"])
        ).fetchone()
        if not row:
            return jsonify({"error": t("api.error.criterionNotFound")}), 404

        body = request.get_json(silent=True) or {}
        new_status = body.get("status")
        if not new_status:
            return jsonify({"error": t("api.error.statusRequired")}), 400
        if new_status not in ("accepted", "rejected"):
            return jsonify({"error": t("api.error.statusMustBeAcceptedOrRejected")}), 400

        db.execute(
            "UPDATE acceptance_criteria SET status = ? WHERE id = ?",
            (new_status, criterion_id)
        )
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/criteria/<int:criterion_id>", methods=["DELETE"])
def delete_criterion(project_id, branch, criterion_id):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        rows = db.execute(
            "DELETE FROM acceptance_criteria WHERE id = ? AND workspace_id = ?",
            (criterion_id, ws["id"])
        ).rowcount
        db.commit()

        if rows == 0:
            return jsonify({"error": t("api.error.criterionNotFound")}), 404

        return jsonify({"ok": True})
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/criteria/<int:criterion_id>/validate", methods=["PUT"])
def validate_criterion_manual(project_id, branch, criterion_id):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        row = db.execute(
            "SELECT id, type FROM acceptance_criteria WHERE id = ? AND workspace_id = ?",
            (criterion_id, ws["id"])
        ).fetchone()
        if not row:
            return jsonify({"error": t("api.error.criterionNotFound")}), 404

        if row["type"] != "custom":
            return jsonify({"error": t("api.error.onlyCustomCriteriaManualValidation")}), 400

        body = request.get_json(silent=True) or {}
        passed = body.get("passed")
        if passed is None:
            return jsonify({"error": t("api.error.passedRequired")}), 400

        validated = 1 if passed else -1
        locale = ws["locale"] if ws["locale"] else "en"
        default_message = t("criteria.validation.manuallyApproved", locale) if passed else t("criteria.validation.rejectedByUser", locale)
        message = body.get("message", default_message)

        db.execute(
            "UPDATE acceptance_criteria SET validated = ?, validation_message = ? WHERE id = ?",
            (validated, message, criterion_id)
        )
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()
