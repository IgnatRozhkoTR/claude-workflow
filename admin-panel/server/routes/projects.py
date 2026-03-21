"""Project CRUD routes."""
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request

from db import get_db
from helpers import run_git, write_json
from i18n import t

bp = Blueprint("projects", __name__)


@bp.route("/api/projects", methods=["GET"])
def list_projects():
    db = get_db()
    try:
        rows = db.execute("SELECT id, name, path, registered FROM projects ORDER BY registered").fetchall()
        projects = [dict(row) for row in rows]
        return jsonify({"projects": projects})
    finally:
        db.close()


@bp.route("/api/projects", methods=["POST"])
def register_project():
    body = request.get_json(silent=True) or {}
    path = body.get("path", "").strip()
    name = body.get("name", "").strip()

    if not path or not os.path.isdir(path):
        return jsonify({"error": t("api.error.invalidDirectoryPath")}), 400

    ok, _, _ = run_git(path, "rev-parse", "--git-dir")
    if not ok:
        run_git(path, "init")
        run_git(path, "checkout", "-b", "develop")
        gitignore = Path(path) / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("")
        run_git(path, "add", ".gitignore")
        run_git(path, "commit", "-m", "Initial commit")

    if not name:
        name = os.path.basename(path)

    project_id = re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())

    db = get_db()
    try:
        existing = db.execute("SELECT id, name, path, registered FROM projects WHERE path = ?", (path,)).fetchone()
        if existing:
            return jsonify({"error": t("api.error.projectAlreadyRegistered"), "project": dict(existing)}), 409

        registered = datetime.now().isoformat()
        db.execute(
            "INSERT INTO projects (id, name, path, registered) VALUES (?, ?, ?, ?)",
            (project_id, name, path, registered)
        )
        db.commit()

        _setup_project_configs(path)

        project = {"id": project_id, "name": name, "path": path, "registered": registered}
        return jsonify(project), 201
    finally:
        db.close()


def _setup_project_configs(project_path):
    provider, host = _detect_git_provider(project_path)

    git_config_path = Path(project_path) / ".claude" / "git-config.json"
    if not git_config_path.exists():
        write_json(git_config_path, {
            "provider": provider,
            "host": host,
            "token": "",
            "default_branch": "develop",
        })

    if provider == "gitlab" and host:
        mcp_path = Path(project_path) / ".mcp.json"
        if not mcp_path.exists():
            write_json(mcp_path, {
                "mcpServers": {
                    "gitlab": {
                        "command": "npx",
                        "args": ["-y", "@zereight/mcp-gitlab"],
                        "env": {
                            "GITLAB_PERSONAL_ACCESS_TOKEN": "",
                            "GITLAB_API_URL": f"https://{host}/api/v4",
                        },
                    }
                }
            })

    _ensure_git_rules_symlink(project_path)


def _detect_git_provider(project_path):
    ok, stdout, _ = run_git(project_path, "remote", "get-url", "origin")
    if not ok or not stdout.strip():
        return "local", ""

    remote_url = stdout.strip()

    if "gitlab" in remote_url:
        host = _extract_host(remote_url)
        return "gitlab", host

    if "github" in remote_url:
        host = _extract_host(remote_url)
        return "github", host

    return "local", ""


def _extract_host(remote_url):
    if remote_url.startswith("http://") or remote_url.startswith("https://"):
        return urlparse(remote_url).hostname or ""
    if remote_url.startswith("git@"):
        match = re.match(r"git@([^:]+):", remote_url)
        return match.group(1) if match else ""
    return ""


def _ensure_git_rules_symlink(project_path):
    rules_path = Path(project_path) / ".claude" / "rules" / "git-rules.md"
    if rules_path.exists() or rules_path.is_symlink():
        return

    system_default = Path("~/.claude/defaults/git-rules.md").expanduser()
    if not system_default.exists():
        return

    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.symlink_to(system_default)


@bp.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    db = get_db()
    try:
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()
