"""Improvement CRUD routes — global (not workspace-scoped)."""
from flask import Blueprint, jsonify, request

import improvement_service
from db import get_db

bp = Blueprint("improvements", __name__)


@bp.route("/api/improvements", methods=["GET"])
def list_improvements():
    scope = request.args.get("scope") or None
    status = request.args.get("status") or None
    db = get_db()
    try:
        items = improvement_service.get_improvements(db, scope=scope, status=status)
        return jsonify({"improvements": items})
    finally:
        db.close()


@bp.route("/api/improvements/<int:improvement_id>/resolve", methods=["PUT"])
def resolve_improvement(improvement_id):
    body = request.get_json(silent=True) or {}
    note = body.get("note", "")
    db = get_db()
    try:
        result = improvement_service.resolve_improvement(db, improvement_id, note=note)
        if "error" in result:
            return jsonify({"error": "Improvement not found"}), 404
        db.commit()
        return jsonify(result)
    finally:
        db.close()


@bp.route("/api/improvements/<int:improvement_id>/reopen", methods=["PUT"])
def reopen_improvement(improvement_id):
    db = get_db()
    try:
        result = improvement_service.reopen_improvement(db, improvement_id)
        if "error" in result:
            return jsonify({"error": "Improvement not found"}), 404
        db.commit()
        return jsonify(result)
    finally:
        db.close()
