"""Git configuration and git rules endpoints."""
import os
from pathlib import Path

from flask import Blueprint, jsonify, request

from core.decorators import with_project
from core.helpers import read_json, write_json

bp = Blueprint("git_config", __name__)

DEFAULTS_GIT_CONFIG = {"provider": "local", "host": "", "token": "", "default_branch": "develop"}
SYSTEM_DEFAULT_GIT_RULES = Path("~/.claude/defaults/git-rules.md").expanduser()


@bp.route("/api/projects/<project_id>/git-config", methods=["GET"])
@with_project
def get_git_config(db, project):
    config_path = Path(project["path"]) / ".claude" / "git-config.json"
    config = read_json(config_path, DEFAULTS_GIT_CONFIG.copy())
    return jsonify(config)


@bp.route("/api/projects/<project_id>/git-config", methods=["PUT"])
@with_project
def save_git_config(db, project):
    body = request.json
    config = {
        "provider": body.get("provider", "local"),
        "host": body.get("host", ""),
        "token": body.get("token", ""),
        "default_branch": body.get("default_branch", "develop"),
    }

    config_path = Path(project["path"]) / ".claude" / "git-config.json"
    write_json(config_path, config)

    mcp_path = Path(project["path"]) / ".mcp.json"
    mcp = read_json(mcp_path, {"mcpServers": {}})
    if "mcpServers" not in mcp:
        mcp["mcpServers"] = {}

    if config["provider"] == "gitlab" and config["host"] and config["token"]:
        mcp["mcpServers"]["gitlab"] = {
            "command": "npx",
            "args": ["-y", "@zereight/mcp-gitlab"],
            "env": {
                "GITLAB_PERSONAL_ACCESS_TOKEN": config["token"],
                "GITLAB_API_URL": f"https://{config['host']}/api/v4",
            },
        }
        write_json(mcp_path, mcp)
    else:
        if "gitlab" in mcp["mcpServers"]:
            del mcp["mcpServers"]["gitlab"]
            write_json(mcp_path, mcp)

    return jsonify({"status": "saved"})


@bp.route("/api/projects/<project_id>/git-rules", methods=["GET"])
@with_project
def get_git_rules(db, project):
    rules_path = Path(project["path"]) / ".claude" / "rules" / "git-rules.md"

    if os.path.islink(rules_path):
        resolved = Path(os.readlink(rules_path)).expanduser()
        if not resolved.is_absolute():
            resolved = (rules_path.parent / resolved).resolve()
        source = "system-default" if resolved == SYSTEM_DEFAULT_GIT_RULES else "project"
        content = rules_path.read_text() if rules_path.exists() else ""
        return jsonify({"content": content, "source": source})

    if rules_path.exists():
        return jsonify({"content": rules_path.read_text(), "source": "project"})

    return jsonify({"content": "", "source": "not-configured"})


@bp.route("/api/projects/<project_id>/git-rules", methods=["PUT"])
@with_project
def save_git_rules(db, project):
    rules_path = Path(project["path"]) / ".claude" / "rules" / "git-rules.md"

    if os.path.islink(rules_path):
        os.remove(rules_path)

    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(request.json.get("content", ""))

    return jsonify({"status": "saved", "source": "project"})
