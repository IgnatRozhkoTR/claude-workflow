"""Static file serving."""
import json
from pathlib import Path

from flask import Blueprint, render_template, send_from_directory

bp = Blueprint("static_files", __name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
_I18N_DIR = TEMPLATES_DIR / "i18n"


@bp.route("/")
def index():
    i18n_path = _I18N_DIR / "en.json"
    i18n_default = json.loads(i18n_path.read_text(encoding="utf-8"))
    return render_template("admin.html", i18n_default=json.dumps(i18n_default))


@bp.route("/css/<path:filename>")
def css_files(filename):
    return send_from_directory(TEMPLATES_DIR / "css", filename)


@bp.route("/js/<path:filename>")
def js_files(filename):
    return send_from_directory(TEMPLATES_DIR / "js", filename)


@bp.route("/i18n/<path:filename>")
def serve_i18n(filename):
    return send_from_directory(TEMPLATES_DIR / "i18n", filename)
