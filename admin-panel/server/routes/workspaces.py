"""Workspace and branch management routes."""
import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request

from core.db import get_db, get_db_ctx
from core.decorators import with_workspace
from core.helpers import sanitize_branch, workspace_dir, run_git, DEFAULT_SOURCE_BRANCH
from core.i18n import t
from core.paths import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_CODEX_DIR,
    DEFAULT_DEFAULTS_DIR,
    DEFAULT_FUNNEL_TEMPLATE,
    DEFAULT_GIT_HOOKS_DIR,
    DEFAULT_HOOKS_DIR,
    DEFAULT_MCP_TEMPLATE,
    DEFAULT_REPO_AGENTS_MD,
    DEFAULT_REPO_CLAUDE_MD,
    DEFAULT_RULES_DIR,
    hook_command,
)
from core.terminal import session_name

bp = Blueprint("workspaces", __name__)


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
    if DEFAULT_FUNNEL_TEMPLATE.exists():
        try:
            template = json.loads(DEFAULT_FUNNEL_TEMPLATE.read_text())
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


_SESSION_START_CMD = hook_command("session-start.py")
_USER_PROMPT_SUBMIT_CMD = hook_command("user-prompt-submit.sh", interpreter="bash")
_PRE_TOOL_HOOK_CMD = hook_command("pre-tool-hook.py")

_WORKSPACE_HOOKS = {
    "hooks": {
        "SessionStart": [
            {
                "matcher": "startup|resume",
                "hooks": [{
                    "type": "command",
                    "command": _SESSION_START_CMD,
                }]
            },
            {
                "matcher": "compact",
                "hooks": [{
                    "type": "command",
                    "command": _SESSION_START_CMD,
                }]
            }
        ],
        "UserPromptSubmit": [{
            "hooks": [{
                "type": "command",
                "command": _USER_PROMPT_SUBMIT_CMD,
            }]
        }],
        "PreToolUse": [{
            "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash|mcp__.*gitlab.*",
            "hooks": [{
                "type": "command",
                "command": _PRE_TOOL_HOOK_CMD,
            }]
        }]
    }
}

_MCP_SERVER_PATH = str(Path(__file__).resolve().parent.parent / "mcp_server.py")

_BACKUP_FILES = [".claude/settings.json", ".mcp.json", "CLAUDE.md", "AGENTS.md"]

_BACKUP_DIRS = [".codex", ".claude/agents", ".claude/hooks"]

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


def _hook_entries_equal(a, b):
    """Return True when two hook-array entries are functionally identical."""
    return a.get("matcher") == b.get("matcher") and a.get("hooks") == b.get("hooks")


def _merge_hook_arrays(existing_entries, governed_entries):
    """Return a merged list: existing entries first, governed entries appended when absent."""
    result = list(existing_entries)
    for governed in governed_entries:
        already_present = any(_hook_entries_equal(governed, e) for e in result)
        if not already_present:
            result.append(governed)
    return result


def _write_workspace_settings(settings_path):
    """Merge governed orchestrator hooks into settings.json at settings_path.

    Reads any pre-existing settings file and merges the governed hook entries
    into each hook_type array rather than overwriting the entire hooks block.
    Pre-existing entries and unrelated hook types are preserved.
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except Exception:
            pass

    existing_hooks = existing.get("hooks", {})
    governed_hooks = _WORKSPACE_HOOKS["hooks"]

    merged_hooks = dict(existing_hooks)
    for hook_type, governed_entries in governed_hooks.items():
        current = merged_hooks.get(hook_type, [])
        merged_hooks[hook_type] = _merge_hook_arrays(current, governed_entries)

    existing["hooks"] = merged_hooks
    settings_path.write_text(json.dumps(existing, indent=2))


def _backup_project_files(project_path):
    """Back up project files and directories before workspace modifications (non-worktree mode).

    Idempotent: existing backups are never overwritten so repeat calls are safe.
    """
    project = Path(project_path)
    for rel in _BACKUP_FILES:
        src = project / rel
        backup = project / (rel + ".pre-workspace")
        if src.exists() and not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, backup)
    for rel in _BACKUP_DIRS:
        src = project / rel
        backup = project / (rel + ".pre-workspace")
        if src.exists() and src.is_dir() and not backup.exists():
            shutil.copytree(src, backup)


def _restore_project_files(project_path):
    """Restore backed-up project files and directories on workspace archive (non-worktree mode)."""
    project = Path(project_path)
    for rel in _BACKUP_FILES:
        backup = project / (rel + ".pre-workspace")
        target = project / rel
        if backup.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
            backup.unlink()
    for rel in _BACKUP_DIRS:
        backup = project / (rel + ".pre-workspace")
        target = project / rel
        if backup.exists() and backup.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(backup, target)
            shutil.rmtree(backup)


_MD_SEPARATOR = "\n\n---\n\n# Governed Workflow Defaults\n\n"

# Repo-default asset directories that are merged into each workspace.
# Each tuple is (source_dir, destination_subpath_inside_workspace).
_REPO_DEFAULT_ASSET_DIRS = [
    (DEFAULT_AGENTS_DIR, Path(".claude") / "agents"),
    (DEFAULT_HOOKS_DIR, Path(".claude") / "hooks"),
    (DEFAULT_RULES_DIR, Path(".claude") / "rules"),
    (DEFAULT_DEFAULTS_DIR, Path(".claude") / "defaults"),
    (DEFAULT_CODEX_DIR, Path(".codex")),
]


def _concatenate_md(repo_default: Path, project_file: Path, workspace_target: Path):
    """Write workspace_target as a merged markdown file.

    If both sources exist, project content appears first, followed by the
    separator and then the repo-default content.  If only one source exists,
    its content is written directly.  If neither exists, nothing is written.
    The workspace target is always a regular file, never a symlink.
    """
    has_default = repo_default.exists()
    has_project = project_file.exists()

    if has_project and has_default:
        content = project_file.read_text() + _MD_SEPARATOR + repo_default.read_text()
    elif has_project:
        content = project_file.read_text()
    elif has_default:
        content = repo_default.read_text()
    else:
        return

    if workspace_target.exists() or workspace_target.is_symlink():
        workspace_target.unlink()
    workspace_target.write_text(content)


def _merge_project_assets(project_path: str, workspace_path: Path):
    """Populate workspace .claude/ and .codex/ via a two-pass merge.

    Pass 1 — repo defaults: for each file under the repo default asset dirs,
    copy it to the equivalent workspace destination ONLY when the destination
    is missing.  Existing destination files are never overwritten.

    Pass 2 — project-local overrides: if the project has its own .claude/ or
    .codex/, walk them and write their files over the workspace copies so the
    project version always wins.

    .claude/worktrees/ is excluded from every pass to prevent recursive copies.
    """
    project = Path(project_path)

    # Pass 1: fill missing files from repo defaults
    for src_dir, dst_rel in _REPO_DEFAULT_ASSET_DIRS:
        if not src_dir.exists():
            continue
        dst_dir = workspace_path / dst_rel
        for src_file in src_dir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            if dst_file.exists():
                continue
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)

    # Pass 2: project-local content overwrites workspace copies (project wins)
    for project_subdir, dst_rel in [
        (project / ".claude", workspace_path / ".claude"),
        (project / ".codex", workspace_path / ".codex"),
    ]:
        if not project_subdir.exists():
            continue
        for src_file in project_subdir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(project_subdir)
            # Never merge content from the worktrees storage root
            if rel.parts and rel.parts[0] == "worktrees":
                continue
            dst_file = dst_rel / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)


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


def _setup_worktree_workspace(project_path, branch, sanitized, source_ref):
    """Create a git worktree for the workspace branch.

    Returns (working_dir, error_response) where error_response is None on success.
    """
    wt_path = Path(project_path) / ".claude" / "worktrees" / sanitized
    if wt_path.exists():
        run_git(project_path, "worktree", "remove", str(wt_path), "--force")
        run_git(project_path, "branch", "-D", branch)

    ok_head, current_branch, _ = run_git(project_path, "symbolic-ref", "--short", "HEAD")
    if ok_head and current_branch.strip() == branch:
        return None, (jsonify({"error": t("api.error.cannotCreateWorktreeCheckedOut", branch=branch)}), 409)

    ok_branch, _, _ = run_git(project_path, "rev-parse", "--verify", f"refs/heads/{branch}")
    if ok_branch:
        ok, stdout, stderr = run_git(project_path, "worktree", "add", str(wt_path), branch)
    else:
        ok, stdout, stderr = run_git(project_path, "worktree", "add", str(wt_path), "-b", branch, source_ref)

    if not ok:
        return None, (jsonify({"error": t("api.error.gitWorktreeAddFailed"), "details": stderr}), 409)

    return str(wt_path), None


def _setup_checkout_workspace(project_path, branch, source_ref):
    """Checkout (or create) a branch in the main repo for non-worktree mode.

    Returns (working_dir, error_response) where error_response is None on success.
    """
    ok_exists, _, _ = run_git(project_path, "rev-parse", "--verify", f"refs/heads/{branch}")
    if ok_exists:
        ok, _, stderr = run_git(project_path, "checkout", branch)
    else:
        ok, _, stderr = run_git(project_path, "checkout", "-b", branch, source_ref)

    if not ok:
        return None, (jsonify({"error": t("api.error.gitCheckoutFailed"), "details": stderr}), 409)

    return project_path, None


def _install_worktree_configs(project_path, wt_path):
    """Populate the worktree with a merged .claude/ and .codex/ from repo defaults and project."""
    wt_path = Path(wt_path)
    dst_claude = wt_path / ".claude"
    src_claude = Path(project_path) / ".claude"

    # a) Merge repo defaults + project-local content into .claude/ and .codex/
    _merge_project_assets(project_path, wt_path)

    # b) Re-establish rules/ and git-config.json as symlinks back to project root
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

    # c) Merge governed hooks into workspace settings.json
    _write_workspace_settings(dst_claude / "settings.json")

    # d) Write CLAUDE.md and AGENTS.md as real concatenated files in the worktree
    _concatenate_md(DEFAULT_REPO_CLAUDE_MD, Path(project_path) / "CLAUDE.md", wt_path / "CLAUDE.md")
    _concatenate_md(DEFAULT_REPO_AGENTS_MD, Path(project_path) / "AGENTS.md", wt_path / "AGENTS.md")

    # e) .codex/ is already populated by _merge_project_assets — no symlink needed.

    # f) Symlink .mcp.json to the project-level file (shared across all worktrees)
    _ensure_project_mcp(project_path)
    src_mcp = Path(project_path) / ".mcp.json"
    dst_mcp = wt_path / ".mcp.json"
    if src_mcp.exists():
        if dst_mcp.exists() or dst_mcp.is_symlink():
            dst_mcp.unlink()
        dst_mcp.symlink_to(src_mcp)

    # g) Install phase-gated git hooks into the worktree
    _install_git_hooks(dst_claude, str(wt_path))


def _install_checkout_configs(project_path):
    """Apply workspace config for checkout (non-worktree) mode.

    The project directory IS the user's permanent root, so this mode is
    conservative: it backs everything up first, then fills in only missing
    pieces from repo defaults without overwriting existing files.
    CLAUDE.md and AGENTS.md are left alone if they already exist.
    """
    _backup_project_files(project_path)

    project = Path(project_path)

    # Fill missing repo-default files — never overwrite existing project files
    for src_dir, dst_rel in _REPO_DEFAULT_ASSET_DIRS:
        if not src_dir.exists():
            continue
        dst_dir = project / dst_rel
        for src_file in src_dir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            if dst_file.exists():
                continue
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)

    # Merge governed hooks into settings.json (union, never overwrite)
    settings_path = project / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    _write_workspace_settings(settings_path)

    # CLAUDE.md / AGENTS.md: copy repo default only when the project has neither
    for repo_default, rel_name in [
        (DEFAULT_REPO_CLAUDE_MD, "CLAUDE.md"),
        (DEFAULT_REPO_AGENTS_MD, "AGENTS.md"),
    ]:
        target = project / rel_name
        if not target.exists() and repo_default.exists():
            shutil.copy2(repo_default, target)

    _ensure_project_mcp(project_path)


def _ensure_project_mcp(project_path):
    """Ensure .mcp.json exists at project level with funnel config and workspace server."""
    mcp_path = Path(project_path) / ".mcp.json"
    if not mcp_path.exists():
        system_mcp = DEFAULT_MCP_TEMPLATE
        if system_mcp.exists():
            shutil.copy2(system_mcp, mcp_path)
        else:
            _generate_mcp_from_remote(project_path)
    _ensure_funnel_config(project_path)
    _ensure_workspace_mcp(mcp_path)


def _install_git_hooks(dst_claude, working_dir):
    """Install phase-gated git hooks into the worktree."""
    hooks_dir = dst_claude / "git-hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    system_hooks = DEFAULT_GIT_HOOKS_DIR
    if system_hooks.exists():
        for hook_name in ["pre-commit", "pre-push"]:
            src_hook = system_hooks / hook_name
            dst_hook = hooks_dir / hook_name
            if src_hook.exists():
                shutil.copy2(src_hook, dst_hook)
                dst_hook.chmod(0o755)

        run_git(working_dir, "config", "extensions.worktreeConfig", "true")
        run_git(working_dir, "config", "--worktree", "core.hooksPath", str(hooks_dir))


def _register_workspace(db, project_id, branch, sanitized, working_dir, source, locale, project_path):
    """Insert workspace into DB and return the creation response."""
    ws_path = workspace_dir(project_path, branch)
    ws_path.mkdir(parents=True, exist_ok=True)

    created = datetime.now().isoformat()

    db.execute(
        "INSERT INTO workspaces (project_id, branch, sanitized_branch, session_id, "
        "working_dir, created, status, phase, scope_json, plan_json, source_branch, locale) "
        "VALUES (?, ?, ?, NULL, ?, ?, 'active', '0', ?, ?, ?, ?)",
        (project_id, branch, sanitized, str(working_dir), created,
         '{}', '{"description":"","systemDiagram":"","execution":[]}', source, locale)
    )
    db.commit()

    tmux_name = session_name(project_id, sanitized)
    command = f"cd {working_dir} && tmux attach -t {tmux_name}"

    return jsonify({
        "workspace": str(ws_path),
        "working_dir": working_dir,
        "branch": branch,
        "command": command
    }), 201


@bp.route("/api/projects/<project_id>/workspaces", methods=["POST"])
def create_workspace(project_id):
    with get_db_ctx() as db:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        body = request.get_json(silent=True) or {}
        branch = body.get("branch", "").strip()
        source = body.get("source", DEFAULT_SOURCE_BRANCH).strip()
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

        existing = db.execute(
            "SELECT id FROM workspaces WHERE project_id = ? AND sanitized_branch = ? AND status = 'active'",
            (project_id, sanitized)
        ).fetchone()
        if existing:
            return jsonify({"error": t("api.error.workspaceAlreadyExists", branch=branch)}), 409

        if use_worktree:
            working_dir, err = _setup_worktree_workspace(project_path, branch, sanitized, source_ref)
            if err:
                return err
            _install_worktree_configs(project_path, working_dir)
        else:
            working_dir, err = _setup_checkout_workspace(project_path, branch, source_ref)
            if err:
                return err
            _install_checkout_configs(project_path)

        return _register_workspace(db, project_id, branch, sanitized, working_dir, source, locale, project_path)


@bp.route("/api/ws/<project_id>/<path:branch>/archive", methods=["PUT"])
@with_workspace
def archive_workspace(db, ws, project):
    if ws["status"] == "archived":
        return jsonify({"error": t("api.error.alreadyArchived")}), 409

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
