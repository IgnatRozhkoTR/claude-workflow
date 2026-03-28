"""Acceptance criteria routes: CRUD and manual validation."""
from flask import Blueprint, jsonify, request

from services import criteria_service
from core.decorators import with_workspace
from core.helpers import VALID_CRITERIA_TYPES
from core.i18n import t

bp = Blueprint("criteria", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/criteria", methods=["GET"])
@with_workspace
def get_criteria(db, ws, project):
    status_filter = request.args.get("status")
    type_filter = request.args.get("type")
    criteria = criteria_service.get_criteria(
        db, ws["id"], status=status_filter, criterion_type=type_filter
    )
    return jsonify({"criteria": criteria})


@bp.route("/api/ws/<project_id>/<path:branch>/criteria", methods=["POST"])
@with_workspace
def create_criterion(db, ws, project):
    body = request.get_json(silent=True) or {}
    criterion_type = body.get("type")
    description = body.get("description")

    if not criterion_type:
        return jsonify({"error": t("api.error.typeRequired")}), 400
    if criterion_type not in VALID_CRITERIA_TYPES:
        return jsonify({"error": t("api.error.invalidCriteriaType", valid_types=", ".join(VALID_CRITERIA_TYPES))}), 400
    if not description:
        return jsonify({"error": t("api.error.descriptionRequired")}), 400

    result = criteria_service.propose_criterion(
        db, ws["id"], criterion_type, description,
        details_json=body.get("details_json"), source="user"
    )
    if "error" in result:
        return jsonify(result), 400
    db.commit()
    return jsonify({"ok": True, "id": result["criterion"]["id"]}), 201


@bp.route("/api/ws/<project_id>/<path:branch>/criteria/<int:criterion_id>", methods=["PUT"])
@with_workspace
def update_criterion(db, ws, project, criterion_id):
    body = request.get_json(silent=True) or {}
    new_status = body.get("status")
    if not new_status:
        return jsonify({"error": t("api.error.statusRequired")}), 400
    if new_status not in ("accepted", "rejected"):
        return jsonify({"error": t("api.error.statusMustBeAcceptedOrRejected")}), 400

    result = criteria_service.set_criterion_status(db, criterion_id, ws["id"], new_status)
    if "error" in result:
        return jsonify({"error": t("api.error.criterionNotFound")}), 404
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/ws/<project_id>/<path:branch>/criteria/<int:criterion_id>", methods=["DELETE"])
@with_workspace
def delete_criterion(db, ws, project, criterion_id):
    result = criteria_service.delete_criterion(db, criterion_id, ws["id"])
    if "error" in result:
        return jsonify({"error": t("api.error.criterionNotFound")}), 404
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/ws/<project_id>/<path:branch>/criteria/<int:criterion_id>/validate", methods=["POST"])
@with_workspace
def validate_criterion(db, ws, project, criterion_id):
    db.execute(
        "UPDATE acceptance_criteria SET validated = 1, validation_message = 'Manually validated by user' WHERE id = ? AND workspace_id = ?",
        (criterion_id, ws["id"])
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/ws/<project_id>/<path:branch>/criteria/<int:criterion_id>/validate", methods=["PUT"])
@with_workspace
def validate_criterion_manual(db, ws, project, criterion_id):
    body = request.get_json(silent=True) or {}
    passed = body.get("passed")
    if passed is None:
        return jsonify({"error": t("api.error.passedRequired")}), 400

    locale = ws["locale"] if ws["locale"] else "en"
    default_message = t("criteria.validation.manuallyApproved", locale) if passed else t("criteria.validation.rejectedByUser", locale)
    message = body.get("message", default_message)

    result = criteria_service.validate_criterion_manual(
        db, criterion_id, ws["id"], passed, message=message
    )
    if "error" in result:
        error_key = result["error"]
        if error_key == "criterion_not_found":
            return jsonify({"error": t("api.error.criterionNotFound")}), 404
        if error_key == "only_custom_criteria":
            return jsonify({"error": t("api.error.onlyCustomCriteriaManualValidation")}), 400
        return jsonify(result), 400
    db.commit()
    return jsonify({"ok": True})
