#!/usr/bin/env python3
"""Workspace Control -- Flask backend for admin panel."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Flask, jsonify
from core.db import init_db
from routes import register_blueprints


def create_app():
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    app = Flask(__name__, static_folder=None, template_folder=str(templates_dir))
    register_blueprints(app)

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(Exception)
    def handle_exception(e):
        return jsonify({"error": str(e)}), 500

    return app


if __name__ == "__main__":
    Path(__file__).resolve().parent.mkdir(parents=True, exist_ok=True)
    init_db()
    app = create_app()
    print("Workspace Control server starting...")
    print(f"  URL: http://localhost:5111")
    app.run(host="0.0.0.0", port=5111, debug=False)
