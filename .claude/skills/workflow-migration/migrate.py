#!/usr/bin/env python3
"""Migrate governed-workflow from system-level ~/.claude to a standalone repo location.

Usage:
    python3 migrate.py <new-repo-path>
    python3 migrate.py <new-repo-path> --dry-run

The script reads the admin-panel database to find all registered projects and
their active workspaces, then updates each workspace's configuration to point
at the new repo location instead of ~/.claude.
"""

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"


def green(msg: str) -> str:
    return f"{GREEN}{msg}{RESET}"


def yellow(msg: str) -> str:
    return f"{YELLOW}{msg}{RESET}"


def red(msg: str) -> str:
    return f"{RED}{msg}{RESET}"


def cyan(msg: str) -> str:
    return f"{CYAN}{msg}{RESET}"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate governed-workflow from system-level ~/.claude to a standalone repo."
    )
    parser.add_argument(
        "new_repo_path",
        metavar="new-repo-path",
        help="Absolute or ~ path to the new governed-workflow repo root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be changed without writing anything.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def load_projects(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, name, path FROM projects").fetchall()


def load_active_workspaces(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, branch, working_dir, status, project_id "
        "FROM workspaces WHERE status != 'archived'"
    ).fetchall()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

OLD_CLAUDE_HOME = Path("~/.claude").expanduser()

OLD_HOOK_PATTERNS = [
    "~/.claude/hooks/",
    str(OLD_CLAUDE_HOME / "hooks") + "/",
]

OLD_TOOLS_PATTERNS = [
    "~/.claude/tools/",
    str(OLD_CLAUDE_HOME / "tools") + "/",
]


def _is_in_place_upgrade(new_repo: Path) -> bool:
    """Return True if the new repo resolves to the same location as ~/.claude."""
    return new_repo == OLD_CLAUDE_HOME


def replace_hook_path(command: str, new_hooks_dir: str) -> tuple[str, bool]:
    """Replace old hook path patterns with the absolute path to <new_repo>/claude/hooks/."""
    updated = command
    for pattern in OLD_HOOK_PATTERNS:
        if pattern in updated:
            updated = updated.replace(pattern, new_hooks_dir)
    return updated, updated != command


def replace_tools_path(command: str) -> tuple[str, bool]:
    """Replace old tools path patterns with ${GOVERNED_WORKFLOW_TOOLS_DIR}/ form."""
    updated = command
    for pattern in OLD_TOOLS_PATTERNS:
        if pattern in updated:
            updated = updated.replace(pattern, "${GOVERNED_WORKFLOW_TOOLS_DIR}/")
    return updated, updated != command


# ---------------------------------------------------------------------------
# Backup helpers
# ---------------------------------------------------------------------------

def backup_file(file_path: Path, dry_run: bool) -> bool:
    """Create a .pre-migration backup of the given file.

    Returns True if a backup was created (or would be created in dry-run).
    Never overwrites an existing backup, making re-runs safe.
    """
    if not file_path.exists():
        return False

    real_path = file_path.resolve()
    backup_path = real_path.parent / (real_path.name + ".pre-migration")

    if backup_path.exists():
        return False

    if not dry_run:
        shutil.copy2(real_path, backup_path)
    return True


# ---------------------------------------------------------------------------
# Block-orchestrator hook injection
# ---------------------------------------------------------------------------

BLOCK_ORCHESTRATOR_MATCHER = "Edit|MultiEdit|Write|NotebookEdit|Bash"


def _has_block_orchestrator_hook(hooks_section: dict) -> bool:
    """Check if block-orchestrator-writes hook already exists in PreToolUse."""
    pre_tool_use = hooks_section.get("PreToolUse", [])
    for hook_group in pre_tool_use:
        for hook in hook_group.get("hooks", []):
            if "block-orchestrator-writes" in hook.get("command", ""):
                return True
    return False


def _make_block_orchestrator_entry(new_hooks_dir: str) -> dict:
    """Create the block-orchestrator-writes hook entry."""
    return {
        "matcher": BLOCK_ORCHESTRATOR_MATCHER,
        "hooks": [{
            "type": "command",
            "command": f"python3 {new_hooks_dir}block-orchestrator-writes.py",
        }],
    }


# ---------------------------------------------------------------------------
# Symlink-aware helpers
# ---------------------------------------------------------------------------

class _ResolvedFileTracker:
    """Tracks which real (resolved) file paths have already been updated.

    In worktree mode, .mcp.json may be a symlink to the project-level file.
    Multiple workspaces can point to the same real file. This tracker prevents
    duplicate writes.
    """

    def __init__(self):
        self._seen: set[Path] = set()

    def already_processed(self, file_path: Path) -> bool:
        real = file_path.resolve()
        if real in self._seen:
            return True
        self._seen.add(real)
        return False


# ---------------------------------------------------------------------------
# Per-workspace operations
# ---------------------------------------------------------------------------

def update_settings_json(
    ws_dir: Path,
    new_hooks_dir: str,
    in_place: bool,
    dry_run: bool,
    backup_counter: list[int],
) -> tuple[bool, str]:
    """Update hook commands in .claude/settings.json.

    Returns (changed, message) where message explains what happened.
    """
    settings_path = ws_dir / ".claude" / "settings.json"
    if not settings_path.exists():
        return False, "not found"

    try:
        raw = settings_path.read_text()
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"ERROR reading: {exc}"

    hooks_section = data.get("hooks", {})
    changed = False

    if not in_place:
        for _event, hook_list in hooks_section.items():
            for hook_group in hook_list:
                for hook in hook_group.get("hooks", []):
                    cmd = hook.get("command", "")
                    new_cmd, was_changed = replace_hook_path(cmd, new_hooks_dir)
                    if was_changed:
                        hook["command"] = new_cmd
                        changed = True

    # Fix legacy .sh extensions (applies in all modes)
    for _event, hook_list in hooks_section.items():
        for hook_group in hook_list:
            for hook in hook_group.get("hooks", []):
                cmd = hook.get("command", "")
                for old_name, new_name in [
                    ("session-start.sh", "session-start.py"),
                    ("pre-tool-hook.sh", "pre-tool-hook.py"),
                    ("block-orchestrator-writes.sh", "block-orchestrator-writes.py"),
                ]:
                    if old_name in cmd:
                        hook["command"] = cmd.replace(old_name, new_name)
                        if hook["command"].startswith("bash "):
                            hook["command"] = "python3 " + hook["command"][5:]
                        changed = True
                        break

    if not _has_block_orchestrator_hook(hooks_section):
        pre_tool_use = hooks_section.setdefault("PreToolUse", [])
        pre_tool_use.insert(0, _make_block_orchestrator_entry(new_hooks_dir))
        data["hooks"] = hooks_section
        changed = True

    if not changed:
        return False, "no changes needed"

    if backup_file(settings_path, dry_run):
        backup_counter[0] += 1

    if not dry_run:
        settings_path.write_text(json.dumps(data, indent=2) + "\n")
    return True, "updated"


def update_mcp_json(
    mcp_path: Path,
    new_repo: Path,
    dry_run: bool,
    file_tracker: _ResolvedFileTracker,
    backup_counter: list[int],
) -> tuple[bool, str]:
    """Update the workspace MCP server path in .mcp.json.

    Returns (changed, message).
    """
    if not mcp_path.exists():
        return False, "not found"

    if file_tracker.already_processed(mcp_path):
        return False, "already updated via symlink"

    try:
        raw = mcp_path.read_text()
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"ERROR reading: {exc}"

    servers = data.get("mcpServers", {})
    workspace_server = servers.get("workspace", {})
    args = workspace_server.get("args", [])

    old_admin_panel = str(OLD_CLAUDE_HOME / "admin-panel")
    new_mcp_server = str(new_repo / "admin-panel" / "server" / "mcp_server.py")
    new_cwd = str(new_repo / "admin-panel" / "server")

    changed = False
    new_args = []
    for arg in args:
        if old_admin_panel in arg or "/.claude/admin-panel" in arg:
            new_args.append(new_mcp_server)
            changed = True
        else:
            new_args.append(arg)

    # Check the command field for old venv paths
    cmd = workspace_server.get("command", "")
    if old_admin_panel in cmd or "/.claude/admin-panel" in cmd:
        workspace_server["command"] = "python3"
        workspace_server["args"] = ["-m", "mcp_server"]
        workspace_server["cwd"] = new_cwd
        changed = True
    elif changed:
        workspace_server["args"] = new_args

    if not changed:
        return False, "no old paths"

    if "cwd" in workspace_server and (
        old_admin_panel in workspace_server.get("cwd", "")
        or "/.claude/admin-panel" in workspace_server.get("cwd", "")
    ):
        workspace_server["cwd"] = new_cwd

    real_path = mcp_path.resolve()
    if backup_file(mcp_path, dry_run):
        backup_counter[0] += 1

    if not dry_run:
        real_path.write_text(json.dumps(data, indent=2) + "\n")
    return True, "updated"


def _is_source_newer(src: Path, dst: Path) -> bool:
    """Return True if src is newer than dst (or dst is missing)."""
    if not dst.exists():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def recopy_hooks(ws_dir: Path, new_repo: Path, dry_run: bool) -> int:
    """Copy hooks from <new-repo>/claude/hooks/ to <workspace>/.claude/hooks/.

    Only copies if the source file is newer than the destination.
    """
    src_hooks = new_repo / "claude" / "hooks"
    dst_hooks = ws_dir / ".claude" / "hooks"

    if not src_hooks.is_dir():
        return 0

    copied = 0
    for src_file in src_hooks.iterdir():
        if not src_file.is_file():
            continue
        dst_file = dst_hooks / src_file.name
        if _is_source_newer(src_file, dst_file):
            if not dry_run:
                dst_hooks.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            copied += 1
    return copied


def recopy_assets(ws_dir: Path, new_repo: Path, dry_run: bool) -> int:
    """Copy missing files from <new-repo>/claude/{agents,rules,defaults}/ to workspace.

    Never overwrites existing files (project-wins semantics).
    Skips rules/ if the destination is a symlink (worktree mode).
    """
    asset_dirs = ["agents", "rules", "defaults"]
    copied = 0

    for dir_name in asset_dirs:
        src_dir = new_repo / "claude" / dir_name
        dst_dir = ws_dir / ".claude" / dir_name

        if not src_dir.is_dir():
            continue

        if dst_dir.is_symlink():
            continue

        for src_file in src_dir.rglob("*"):
            if not src_file.is_file():
                continue
            relative = src_file.relative_to(src_dir)
            dst_file = dst_dir / relative
            if not dst_file.exists():
                if not dry_run:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                copied += 1

    return copied


def recopy_codex(ws_dir: Path, new_repo: Path, dry_run: bool) -> int:
    """Copy files from <new-repo>/codex/ to <workspace>/.codex/.

    If .codex is a symlink, remove it and create a real directory populated
    from the new repo's codex/ folder. Otherwise, copy only missing files
    (project-wins semantics).
    """
    src_codex = new_repo / "codex"
    dst_codex = ws_dir / ".codex"

    if not src_codex.is_dir():
        return 0

    if dst_codex.is_symlink():
        if not dry_run:
            dst_codex.unlink()
            dst_codex.mkdir(parents=True, exist_ok=True)

        copied = 0
        for src_file in src_codex.rglob("*"):
            if not src_file.is_file():
                continue
            relative = src_file.relative_to(src_codex)
            dst_file = dst_codex / relative
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            copied += 1
        return copied

    copied = 0
    for src_file in src_codex.rglob("*"):
        if not src_file.is_file():
            continue
        relative = src_file.relative_to(src_codex)
        dst_file = dst_codex / relative
        if not dst_file.exists():
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            copied += 1

    return copied


# ---------------------------------------------------------------------------
# Project-level config updates
# ---------------------------------------------------------------------------

def update_project_mcp(
    project_path: Path,
    new_repo: Path,
    dry_run: bool,
    file_tracker: _ResolvedFileTracker,
    backup_counter: list[int],
) -> tuple[bool, str]:
    """Update <project>/.mcp.json if it has old admin-panel paths.

    Catches projects with no active workspaces.
    """
    mcp_path = project_path / ".mcp.json"
    return update_mcp_json(mcp_path, new_repo, dry_run, file_tracker, backup_counter)


# ---------------------------------------------------------------------------
# DB update
# ---------------------------------------------------------------------------

def update_verification_steps(conn: sqlite3.Connection, dry_run: bool) -> int:
    """Replace ~/.claude/tools/ with ${GOVERNED_WORKFLOW_TOOLS_DIR}/ in verification_steps."""
    rows = conn.execute("SELECT id, command FROM verification_steps").fetchall()
    updated = 0

    for row in rows:
        cmd = row["command"] or ""
        new_cmd, changed = replace_tools_path(cmd)
        if changed:
            updated += 1
            if not dry_run:
                conn.execute(
                    "UPDATE verification_steps SET command = ? WHERE id = ?",
                    (new_cmd, row["id"]),
                )

    if not dry_run and updated:
        conn.commit()

    return updated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def resolve_repo(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def workspace_dir(ws: sqlite3.Row) -> Path | None:
    working_dir = ws["working_dir"]
    if not working_dir:
        return None
    p = Path(working_dir).expanduser()
    if not p.is_dir():
        return None
    return p


def main() -> None:
    args = parse_args()
    new_repo = resolve_repo(args.new_repo_path)
    dry_run: bool = args.dry_run
    in_place = _is_in_place_upgrade(new_repo)

    db_path = new_repo / "admin-panel" / "server" / "admin-panel.db"
    if not db_path.exists():
        print(red(f"ERROR: database not found at {db_path}"))
        print(f"  Make sure <new-repo-path> is the root of the governed-workflow repo.")
        sys.exit(1)

    new_hooks_dir = str(new_repo / "claude" / "hooks") + "/"

    print(f"New repo  : {new_repo}")
    print(f"Hooks dir : {new_hooks_dir}")
    print(f"Database  : {db_path}")
    print(f"Dry-run   : {dry_run}")

    if in_place:
        print(f"\n{yellow('NOTE')}: New repo resolves to ~/.claude — in-place upgrade detected.")
        print(f"  Hook path replacements in settings.json will be skipped (paths unchanged).")
        print(f"  Missing hooks and assets will still be added.\n")
    else:
        print()

    if not dry_run:
        answer = input("Apply changes to all active workspaces? [y/N] ").strip().lower()
        if answer != "y":
            print(yellow("Aborted."))
            sys.exit(0)
        print()

    conn = open_db(db_path)
    file_tracker = _ResolvedFileTracker()

    projects_by_id = {row["id"]: row for row in load_projects(conn)}
    workspaces = load_active_workspaces(conn)

    total_ws = 0
    total_settings = 0
    total_mcp = 0
    total_hooks = 0
    total_assets = 0
    total_codex = 0
    total_projects_mcp = 0
    backup_counter = [0]
    skipped: list[tuple[str, str]] = []

    for ws in workspaces:
        project = projects_by_id.get(ws["project_id"])
        project_name = project["name"] if project else f"project#{ws['project_id']}"
        branch = ws["branch"] or "<no branch>"

        print(f"Workspace: {project_name} / {branch}  (status={ws['status']})")

        ws_dir = workspace_dir(ws)
        if ws_dir is None:
            reason = f"working_dir missing or not found: {ws['working_dir']}"
            print(f"  {yellow('SKIP')} {reason}")
            skipped.append((f"{project_name}/{branch}", reason))
            continue

        total_ws += 1

        # settings.json
        changed, msg = update_settings_json(
            ws_dir, new_hooks_dir, in_place, dry_run, backup_counter,
        )
        if changed:
            total_settings += 1
            tag = "WOULD UPDATE" if dry_run else "UPDATED"
            print(f"  {green(tag)} .claude/settings.json ({msg})")
        elif "ERROR" in msg:
            print(f"  {red(msg)}")
        else:
            print(f"  {yellow('OK')} .claude/settings.json ({msg})")

        # .mcp.json
        mcp_path = ws_dir / ".mcp.json"
        changed, msg = update_mcp_json(
            mcp_path, new_repo, dry_run, file_tracker, backup_counter,
        )
        if changed:
            total_mcp += 1
            tag = "WOULD UPDATE" if dry_run else "UPDATED"
            print(f"  {green(tag)} .mcp.json ({msg})")
        else:
            print(f"  {yellow('OK')} .mcp.json ({msg})")

        # hooks
        n = recopy_hooks(ws_dir, new_repo, dry_run)
        if n:
            total_hooks += n
            tag = "WOULD COPY" if dry_run else "COPIED"
            print(f"  {green(tag)} {n} hook file(s) to .claude/hooks/")
        else:
            print(f"  {yellow('OK')} .claude/hooks/ (all up to date)")

        # agents/rules/defaults
        n = recopy_assets(ws_dir, new_repo, dry_run)
        if n:
            total_assets += n
            tag = "WOULD COPY" if dry_run else "COPIED"
            print(f"  {green(tag)} {n} missing asset file(s) to .claude/")
        else:
            print(f"  {yellow('OK')} .claude/ assets (nothing missing)")

        # .codex
        n = recopy_codex(ws_dir, new_repo, dry_run)
        if n:
            total_codex += n
            tag = "WOULD COPY" if dry_run else "COPIED"
            print(f"  {green(tag)} {n} codex file(s) to .codex/")
        else:
            print(f"  {yellow('OK')} .codex/ (nothing missing)")

    # Project-level .mcp.json updates
    print()
    print(cyan("--- Project-level configs ---"))
    all_projects = load_projects(conn)
    for proj in all_projects:
        proj_path = Path(proj["path"]).expanduser()
        if not proj_path.is_dir():
            print(f"  {yellow('SKIP')} {proj['name']}: path not found ({proj['path']})")
            continue

        changed, msg = update_project_mcp(
            proj_path, new_repo, dry_run, file_tracker, backup_counter,
        )
        if changed:
            total_projects_mcp += 1
            tag = "WOULD UPDATE" if dry_run else "UPDATED"
            print(f"  {green(tag)} {proj['name']}/.mcp.json ({msg})")
        else:
            print(f"  {yellow('OK')} {proj['name']}/.mcp.json ({msg})")

    # DB verification_steps
    print()
    try:
        n = update_verification_steps(conn, dry_run)
        if n:
            tag = "WOULD UPDATE" if dry_run else "UPDATED"
            print(f"{green(tag)} {n} verification_steps row(s) in DB")
        else:
            print(f"{yellow('OK')} verification_steps (no old tool paths)")
    except sqlite3.OperationalError:
        print(f"{yellow('SKIP')} verification_steps table not found (pre-0017 schema)")

    conn.close()

    # Summary
    print()
    print("--- Summary ---")
    print(f"  Workspaces processed : {total_ws}")
    print(f"  settings.json updated: {total_settings}")
    print(f"  .mcp.json updated    : {total_mcp} workspace(s) + {total_projects_mcp} project(s)")
    print(f"  Hook files copied    : {total_hooks}")
    print(f"  Asset files copied   : {total_assets}")
    print(f"  Codex files copied   : {total_codex}")
    print(f"  Files backed up      : {backup_counter[0]}")

    if skipped:
        print()
        print(f"  Skipped workspaces ({len(skipped)}):")
        for name, reason in skipped:
            print(f"    - {name}: {reason}")

    print()
    if dry_run:
        print(yellow("Dry-run complete. Re-run without --dry-run to apply."))
    else:
        print(green("Migration complete."))
    print(f"  Safe to re-run: backups are never overwritten (.pre-migration files preserved).")


if __name__ == "__main__":
    main()
