"""Verification profile CRUD and results routes."""
from flask import Blueprint, jsonify, request

from services import verification_service
from core.decorators import with_workspace
from core.db import get_db_ctx

bp = Blueprint("verification", __name__)


@bp.route("/api/verification/profiles", methods=["GET"])
def list_profiles():
    """List all verification profiles (global, not workspace-scoped)."""
    with get_db_ctx() as db:
        profiles = verification_service.get_all_profiles(db)
        return jsonify({"profiles": profiles})


@bp.route("/api/verification/profiles", methods=["POST"])
def create_profile():
    """Create a new verification profile."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    language = body.get("language", "").strip()
    description = body.get("description", "").strip()
    if not name or not language:
        return jsonify({"error": "name and language are required"}), 400
    with get_db_ctx() as db:
        result = verification_service.create_profile(db, name, language, description=description or None)
        db.commit()
        return jsonify(result)


@bp.route("/api/verification/profiles/<int:profile_id>", methods=["DELETE"])
def delete_profile(profile_id):
    """Delete a verification profile and all associated data."""
    with get_db_ctx() as db:
        result = verification_service.delete_profile(db, profile_id)
        if not result:
            return jsonify({"error": "Profile not found"}), 404
        db.commit()
        return jsonify({"ok": True, "deleted": result})


@bp.route("/api/verification/profiles/<int:profile_id>/steps", methods=["POST"])
def add_step(profile_id):
    """Add a step to a profile."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    command = body.get("command", "").strip()
    if not name or not command:
        return jsonify({"error": "name and command are required"}), 400
    with get_db_ctx() as db:
        result = verification_service.add_step(
            db, profile_id, name, command,
            description=body.get("description"),
            install_check_command=body.get("install_check_command"),
            install_command=body.get("install_command"),
            enabled=body.get("enabled", True),
            sort_order=body.get("sort_order", 0),
            timeout=body.get("timeout", 120),
            fail_severity=body.get("fail_severity", "blocking"),
        )
        if "error" in result:
            return jsonify(result), 404
        db.commit()
        return jsonify(result)


@bp.route("/api/verification/steps/<int:step_id>", methods=["PUT"])
def update_step(step_id):
    """Update a verification step."""
    body = request.get_json(silent=True) or {}
    with get_db_ctx() as db:
        result = verification_service.update_step(db, step_id, **body)
        if "error" in result:
            code = 404 if result["error"] == "step_not_found" else 400
            return jsonify(result), code
        db.commit()
        return jsonify(result)


@bp.route("/api/verification/steps/<int:step_id>", methods=["DELETE"])
def delete_step(step_id):
    """Delete a verification step."""
    with get_db_ctx() as db:
        result = verification_service.delete_step(db, step_id)
        if "error" in result:
            return jsonify(result), 404
        db.commit()
        return jsonify(result)


@bp.route("/api/ws/<project_id>/<path:branch>/verification/profiles", methods=["GET"])
@with_workspace
def get_workspace_profiles(db, ws, project):
    """Get profiles assigned to this workspace's project."""
    profiles = verification_service.get_project_profiles(db, project["id"])
    return jsonify({"profiles": profiles})


@bp.route("/api/ws/<project_id>/<path:branch>/verification/assign", methods=["POST"])
@with_workspace
def assign_profile(db, ws, project):
    """Assign a profile to this workspace's project."""
    body = request.get_json(silent=True) or {}
    profile_id = body.get("profile_id")
    subpath = body.get("subpath", ".")
    if not profile_id:
        return jsonify({"error": "profile_id is required"}), 400
    result = verification_service.assign_profile(db, project["id"], profile_id, subpath=subpath)
    if "error" in result:
        code = 409 if result["error"] == "already_assigned" else 404
        return jsonify(result), code
    db.commit()
    return jsonify(result)


@bp.route("/api/ws/<project_id>/<path:branch>/verification/unassign/<int:assignment_id>", methods=["DELETE"])
@with_workspace
def unassign_profile(db, ws, project, assignment_id):
    """Remove a profile assignment from this workspace's project."""
    result = verification_service.unassign_profile(db, assignment_id, project["id"])
    if "error" in result:
        return jsonify(result), 404
    db.commit()
    return jsonify(result)


@bp.route("/api/ws/<project_id>/<path:branch>/verification/results", methods=["GET"])
@with_workspace
def get_results(db, ws, project):
    """Get verification results for this workspace."""
    phase = request.args.get("phase")
    run_id = request.args.get("run_id", type=int)
    result = verification_service.get_verification_results(
        db, ws["id"], phase=phase, run_id=run_id
    )
    if not result:
        return jsonify({"message": "No verification runs found"}), 200
    return jsonify(result)


@bp.route("/api/ws/<project_id>/<path:branch>/verification/run", methods=["POST"])
@with_workspace
def run_verification(db, ws, project):
    """Manually trigger verification for the current workspace."""
    body = request.get_json(silent=True) or {}
    phase = body.get("phase", ws["phase"])
    passed, run_id = verification_service.run_verification(db, ws["id"], phase, ws["working_dir"])
    db.commit()
    if run_id is None:
        return jsonify({"message": "No verification profiles assigned"}), 200
    result = verification_service.get_verification_results(db, ws["id"], run_id=run_id)
    return jsonify(result)
