"""Workspace and branch management routes."""
import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request

from db import get_db
from helpers import sanitize_branch, workspace_dir, run_git, find_workspace
from i18n import t

bp = Blueprint("workspaces", __name__)

_FUNNEL_TEMPLATE = Path.home() / ".claude" / "defaults" / ".mcp-funnel.json"


def _get_gitlab_from_remote(project_path):
    """Extract GitLab host and token from git remote + git-config.json. Returns (host, token) or None."""
    ok, remote_url, _ = run_git(project_path, "remote", "get-url", "origin")
    if not ok or not remote_url.strip():
        return None

    remote_url = remote_url.strip()

    if remote_url.startswith("http"):
        host = urlparse(remote_url).hostname
    elif "@" in remote_url:
        host = remote_url.split("@")[1].split(":")[0]
    else:
        return None

    if not host or "gitlab" not in host.lower():
        return None

    token = ""
    config_path = Path(project_path) / ".claude" / "git-config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                token = json.load(f).get("token", "")
        except Exception:
            pass

    return host, token


def _generate_mcp_from_remote(project_path):
    """Generate .mcp-funnel.json and .mcp.json at project level from git remote."""
    gitlab = _get_gitlab_from_remote(project_path)
    if not gitlab:
        return

    host, token = gitlab
    _write_funnel_config(project_path, host, token)

    mcp_data = {
        "mcpServers": {
            "gitlab": {
                "command": "npx",
                "args": ["-y", "mcp-funnel", "--config", ".mcp-funnel.json"]
            }
        }
    }
    project_mcp = Path(project_path) / ".mcp.json"
    with open(project_mcp, "w") as f:
        json.dump(mcp_data, f, indent=2)


def _write_funnel_config(project_path, host, token):
    """Write .mcp-funnel.json from default template + gitlab server config."""
    template = {}
    if _FUNNEL_TEMPLATE.exists():
        try:
            template = json.loads(_FUNNEL_TEMPLATE.read_text())
        except Exception:
            pass

    template["servers"] = {
        "gitlab": {
            "command": "npx",
            "args": ["-y", "@zereight/mcp-gitlab"],
            "env": {
                "GITLAB_PERSONAL_ACCESS_TOKEN": token,
                "GITLAB_API_URL": f"https://{host}/api/v4"
            }
        }
    }

    project_funnel = Path(project_path) / ".mcp-funnel.json"
    with open(project_funnel, "w") as f:
        json.dump(template, f, indent=2)


def _ensure_funnel_config(project_path):
    """Ensure .mcp-funnel.json exists. Migrates direct gitlab entries in .mcp.json to funnel."""
    project_funnel = Path(project_path) / ".mcp-funnel.json"
    if project_funnel.exists():
        return

    project_mcp = Path(project_path) / ".mcp.json"
    if not project_mcp.exists():
        return

    try:
        mcp_data = json.loads(project_mcp.read_text())
    except Exception:
        return

    servers = mcp_data.get("mcpServers", {})
    gitlab_entry = servers.get("gitlab", {})
    args = gitlab_entry.get("args", [])

    if "@zereight/mcp-gitlab" not in args:
        return

    # Extract host from env
    env = gitlab_entry.get("env", {})
    api_url = env.get("GITLAB_API_URL", "")
    token = env.get("GITLAB_PERSONAL_ACCESS_TOKEN", "")
    # Parse host from API URL (https://host/api/v4 → host)
    host = api_url.replace("https://", "").replace("/api/v4", "").strip("/") if api_url else ""

    if host:
        _write_funnel_config(project_path, host, token)
    else:
        # Fallback: try git remote
        gitlab = _get_gitlab_from_remote(project_path)
        if gitlab:
            _write_funnel_config(project_path, gitlab[0], gitlab[1])
        else:
            return

    servers["gitlab"] = {
        "command": "npx",
        "args": ["-y", "mcp-funnel", "--config", ".mcp-funnel.json"]
    }
    project_mcp.write_text(json.dumps(mcp_data, indent=2))


_WORKSPACE_HOOKS = {
    "hooks": {
        "SessionStart": [
            {
                "matcher": "startup|resume",
                "hooks": [{
                    "type": "command",
                    "command": "bash ~/.claude/hooks/session-start.sh"
                }]
            },
            {
                "matcher": "compact",
                "hooks": [{
                    "type": "command",
                    "command": "bash ~/.claude/hooks/session-start.sh"
                }]
            }
        ],
        "UserPromptSubmit": [{
            "hooks": [{
                "type": "command",
                "command": "bash ~/.claude/hooks/user-prompt-submit.sh"
            }]
        }],
        "PreToolUse": [{
            "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash|mcp__.*gitlab.*",
            "hooks": [{
                "type": "command",
                "command": "bash ~/.claude/hooks/pre-tool-hook.sh"
            }]
        }]
    }
}

_MCP_SERVER_PATH = str(Path(__file__).resolve().parent.parent / "mcp_server.py")

_BACKUP_FILES = [".claude/settings.json", ".mcp.json", "CLAUDE.md"]

_SYMLINK_TO_PROJECT = ["rules", "git-config.json"]


def _ensure_workspace_mcp(mcp_path):
    """Ensure the workspace MCP server is present in .mcp.json."""
    data = {}
    if mcp_path.exists():
        try:
            data = json.loads(mcp_path.read_text())
        except Exception:
            pass
    servers = data.setdefault("mcpServers", {})
    if "workspace" not in servers:
        servers["workspace"] = {
            "command": "python3",
            "args": [_MCP_SERVER_PATH]
        }
        mcp_path.write_text(json.dumps(data, indent=2))


def _write_workspace_settings(settings_path):
    """Write orchestrator hook settings to the given path."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except Exception:
            pass
    existing["hooks"] = _WORKSPACE_HOOKS["hooks"]
    settings_path.write_text(json.dumps(existing, indent=2))


def _backup_project_files(project_path):
    """Back up project files before workspace modifications (non-worktree mode)."""
    project = Path(project_path)
    for rel in _BACKUP_FILES:
        src = project / rel
        backup = project / (rel + ".pre-workspace")
        if src.exists() and not backup.exists():
            shutil.copy2(src, backup)


def _restore_project_files(project_path):
    """Restore backed-up project files on workspace archive (non-worktree mode)."""
    project = Path(project_path)
    for rel in _BACKUP_FILES:
        backup = project / (rel + ".pre-workspace")
        target = project / rel
        if backup.exists():
            shutil.copy2(backup, target)
            backup.unlink()


@bp.route("/api/projects/<project_id>/branches", methods=["GET"])
def list_branches(project_id):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404
    finally:
        db.close()

    has_remote, remotes, _ = run_git(project["path"], "remote")
    if has_remote and remotes.strip():
        run_git(project["path"], "fetch", "--prune")

    ok, stdout, _ = run_git(project["path"], "branch", "-a", "--format=%(refname:short)")
    if not ok:
        return jsonify({"error": t("api.error.failedToListBranches")}), 500

    branches = [b.strip() for b in stdout.strip().split("\n") if b.strip()]

    local = []
    remote = []
    for b in branches:
        if b.startswith("origin/"):
            name = b[7:]
            if name != "HEAD":
                remote.append(name)
        else:
            local.append(b)

    return jsonify({"local": local, "remote": remote})


@bp.route("/api/projects/<project_id>/workspaces", methods=["GET"])
def list_workspaces(project_id):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        rows = db.execute(
            "SELECT id, sanitized_branch, branch, session_id, working_dir, phase, status, created "
            "FROM workspaces WHERE project_id = ? ORDER BY created",
            (project_id,)
        ).fetchall()

        ws_ids = [row["id"] for row in rows]
        sessions_by_ws = {}
        if ws_ids:
            placeholders = ",".join("?" * len(ws_ids))
            session_rows = db.execute(
                f"SELECT workspace_id, session_id, started_at FROM session_history "
                f"WHERE workspace_id IN ({placeholders}) ORDER BY id DESC",
                ws_ids
            ).fetchall()
            for sr in session_rows:
                sessions_by_ws.setdefault(sr["workspace_id"], []).append({
                    "session_id": sr["session_id"],
                    "started_at": sr["started_at"]
                })

        workspaces = []
        for row in rows:
            workspaces.append({
                "id": row["sanitized_branch"],
                "branch": row["branch"],
                "phase": row["phase"],
                "session_id": row["session_id"],
                "working_dir": row["working_dir"],
                "status": row["status"],
                "created": row["created"],
                "sessions": sessions_by_ws.get(row["id"], []),
            })

        return jsonify({"workspaces": workspaces})
    finally:
        db.close()


@bp.route("/api/projects/<project_id>/workspaces", methods=["POST"])
def create_workspace(project_id):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404
    finally:
        db.close()

    body = request.json
    branch = body.get("branch", "").strip()
    source = body.get("source", "develop").strip()
    use_worktree = body.get("worktree", True)
    locale = body.get("locale", "en").strip()

    if not branch:
        return jsonify({"error": t("api.error.branchNameRequired")}), 400

    project_path = project["path"]
    sanitized = sanitize_branch(branch)

    ok, _, _ = run_git(project_path, "rev-parse", "--is-inside-work-tree")
    if not ok:
        run_git(project_path, "init")
        run_git(project_path, "commit", "--allow-empty", "-m", "Initial commit")

    has_remote, remotes, _ = run_git(project_path, "remote")
    if has_remote and remotes.strip():
        run_git(project_path, "fetch", "origin")

    source_ref = f"origin/{source}"
    ok, _, _ = run_git(project_path, "rev-parse", "--verify", source_ref)
    if not ok:
        ok, _, _ = run_git(project_path, "rev-parse", "--verify", source)
        if not ok:
            return jsonify({"error": t("api.error.sourceBranchNotFound", source=source)}), 404
        source_ref = source

    # Check for active workspace with the same branch
    check_db = get_db()
    try:
        existing = check_db.execute(
            "SELECT id FROM workspaces WHERE project_id = ? AND sanitized_branch = ? AND status = 'active'",
            (project_id, sanitized)
        ).fetchone()
        if existing:
            return jsonify({"error": t("api.error.workspaceAlreadyExists", branch=branch)}), 409
    finally:
        check_db.close()

    if use_worktree:
        wt_path = Path(project_path) / ".claude" / "worktrees" / sanitized
        if wt_path.exists():
            # Stale worktree — clean up
            run_git(project_path, "worktree", "remove", str(wt_path), "--force")
            # Also delete the branch if it exists
            run_git(project_path, "branch", "-D", branch)

        # Can't create worktree for the currently checked-out branch
        ok_head, current_branch, _ = run_git(project_path, "symbolic-ref", "--short", "HEAD")
        if ok_head and current_branch.strip() == branch:
            return jsonify({"error": t("api.error.cannotCreateWorktreeCheckedOut", branch=branch)}), 409

        # Check if branch already exists
        ok_branch, _, _ = run_git(project_path, "rev-parse", "--verify", f"refs/heads/{branch}")
        if ok_branch:
            # Branch exists — use it without -b
            ok, stdout, stderr = run_git(
                project_path, "worktree", "add", str(wt_path), branch
            )
        else:
            # Create new branch
            ok, stdout, stderr = run_git(
                project_path, "worktree", "add", str(wt_path), "-b", branch, source_ref
            )
        if not ok:
            return jsonify({"error": t("api.error.gitWorktreeAddFailed"), "details": stderr}), 409

        working_dir = str(wt_path)

        # Copy .claude/ from project into worktree (isolated, removed with worktree)
        src_claude = Path(project_path) / ".claude"
        dst_claude = wt_path / ".claude"
        if src_claude.exists():
            dst_claude.mkdir(parents=True, exist_ok=True)
            for item in src_claude.iterdir():
                if item.name == "worktrees":
                    continue
                dst_item = dst_claude / item.name
                if dst_item.exists() or dst_item.is_symlink():
                    if dst_item.is_dir() and not dst_item.is_symlink():
                        shutil.rmtree(dst_item)
                    else:
                        dst_item.unlink()
                if item.is_dir():
                    shutil.copytree(item, dst_item, symlinks=True)
                else:
                    shutil.copy2(item, dst_item)

            # Symlink shared configs back to project (changes persist across worktrees)
            for rel in _SYMLINK_TO_PROJECT:
                dst = dst_claude / rel
                src = src_claude / rel
                if src.exists():
                    if dst.exists() or dst.is_symlink():
                        if dst.is_dir() and not dst.is_symlink():
                            shutil.rmtree(dst)
                        else:
                            dst.unlink()
                    dst.symlink_to(src)

        # Write orchestrator hooks into the worktree's own settings
        _write_workspace_settings(dst_claude / "settings.json")

        # Copy CLAUDE.md if it exists at project root
        src_claude_md = Path(project_path) / "CLAUDE.md"
        dst_claude_md = wt_path / "CLAUDE.md"
        if src_claude_md.exists():
            if dst_claude_md.exists() or dst_claude_md.is_symlink():
                dst_claude_md.unlink()
            dst_claude_md.symlink_to(src_claude_md)

        # Copy .mcp.json into worktree
        src_mcp = Path(project_path) / ".mcp.json"
        if not src_mcp.exists():
            system_mcp = Path.home() / ".claude" / ".mcp.json"
            if system_mcp.exists():
                shutil.copy2(system_mcp, src_mcp)
            else:
                _generate_mcp_from_remote(project_path)

        _ensure_funnel_config(project_path)
        _ensure_workspace_mcp(src_mcp)
        dst_mcp = wt_path / ".mcp.json"
        if src_mcp.exists():
            if dst_mcp.exists() or dst_mcp.is_symlink():
                dst_mcp.unlink()
            dst_mcp.symlink_to(src_mcp)

        # Install phase-gated git hooks
        hooks_dir = dst_claude / "git-hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        system_hooks = Path.home() / ".claude" / "defaults" / "git-hooks"
        if system_hooks.exists():
            for hook_name in ["pre-commit", "pre-push"]:
                src_hook = system_hooks / hook_name
                dst_hook = hooks_dir / hook_name
                if src_hook.exists():
                    shutil.copy2(src_hook, dst_hook)
                    dst_hook.chmod(0o755)

            run_git(str(wt_path), "config", "extensions.worktreeConfig", "true")
            run_git(str(wt_path), "config", "--worktree", "core.hooksPath", str(hooks_dir))
    else:
        # Check if branch already exists
        ok_exists, _, _ = run_git(project_path, "rev-parse", "--verify", f"refs/heads/{branch}")
        if ok_exists:
            # Branch exists — just checkout
            ok, _, stderr = run_git(project_path, "checkout", branch)
        else:
            # Create new branch
            ok, _, stderr = run_git(project_path, "checkout", "-b", branch, source_ref)
        if not ok:
            return jsonify({"error": t("api.error.gitCheckoutFailed"), "details": stderr}), 409
        working_dir = project_path

        # Back up original files before writing workspace settings
        _backup_project_files(project_path)
        # Write orchestrator hooks
        settings_path = Path(project_path) / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        _write_workspace_settings(settings_path)
        # Ensure .mcp.json exists
        mcp_path = Path(project_path) / ".mcp.json"
        if not mcp_path.exists():
            system_mcp = Path.home() / ".claude" / ".mcp.json"
            if system_mcp.exists():
                shutil.copy2(system_mcp, mcp_path)
            else:
                _generate_mcp_from_remote(project_path)
        _ensure_funnel_config(project_path)
        _ensure_workspace_mcp(mcp_path)

    ws_path = workspace_dir(project_path, branch)
    ws_path.mkdir(parents=True, exist_ok=True)

    created = datetime.now().isoformat()

    db = get_db()
    try:
        db.execute(
            "INSERT INTO workspaces (project_id, branch, sanitized_branch, session_id, "
            "working_dir, created, status, phase, scope_json, plan_json, source_branch, locale) "
            "VALUES (?, ?, ?, NULL, ?, ?, 'active', '0', ?, ?, ?, ?)",
            (project_id, branch, sanitized, str(working_dir), created,
             '{}', '{"description":"","systemDiagram":"","execution":[]}', source, locale)
        )
        db.commit()

        command = f"cd {working_dir} && claude --dangerously-skip-permissions"

        return jsonify({
            "workspace": str(ws_path),
            "working_dir": working_dir,
            "branch": branch,
            "command": command
        }), 201
    finally:
        db.close()


@bp.route("/api/ws/<project_id>/<path:branch>/archive", methods=["PUT"])
def archive_workspace(project_id, branch):
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        if ws["status"] == "archived":
            return jsonify({"error": t("api.error.alreadyArchived")}), 409

        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        project_path = project["path"]
        working_dir = ws["working_dir"]
        is_worktree = working_dir != project_path

        if is_worktree:
            wt_path = Path(working_dir)
            if wt_path.exists():
                # Preserve workspace metadata before removing the worktree
                sanitized = sanitize_branch(ws["branch"])
                wt_ws_dir = wt_path / ".claude" / "workspaces" / sanitized
                proj_ws_dir = Path(project_path) / ".claude" / "workspaces" / sanitized
                if wt_ws_dir.exists():
                    if proj_ws_dir.exists():
                        shutil.rmtree(proj_ws_dir)
                    shutil.copytree(wt_ws_dir, proj_ws_dir)

                run_git(project_path, "worktree", "remove", str(wt_path), "--force")
        else:
            _restore_project_files(project_path)

        archived_key = ws["sanitized_branch"] + "--" + datetime.now().strftime("%Y%m%d-%H%M%S")
        db.execute(
            "UPDATE workspaces SET status = 'archived', sanitized_branch = ? WHERE id = ?",
            (archived_key, ws["id"])
        )
        db.commit()

        return jsonify({"status": "archived", "branch": ws["branch"]})
    finally:
        db.close()
