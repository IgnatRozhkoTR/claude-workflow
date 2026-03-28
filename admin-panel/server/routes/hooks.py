"""Session hook routes."""
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from core.db import get_db
from core.helpers import find_workspace, run_git, workspace_dir
from core.i18n import t

bp = Blueprint("hooks", __name__)


@bp.route("/api/hook/session-start", methods=["POST"])
def session_start_hook():
    body = request.json or {}
    session_id = body.get("session_id", "")
    cwd = body.get("cwd", "")

    if not session_id:
        return jsonify({"error": t("api.error.sessionIdRequired")}), 400

    search_dir = Path(cwd) if cwd else Path.cwd()

    ok, git_root, _ = run_git(str(search_dir), "rev-parse", "--show-toplevel")
    if not ok:
        return jsonify({"ok": False, "message": t("api.error.noWorkspaceForCwd")})

    git_root = git_root.strip()
    ok2, branch_name, _ = run_git(git_root, "rev-parse", "--abbrev-ref", "HEAD")
    if not ok2:
        return jsonify({"ok": False, "message": t("api.error.noWorkspaceForCwd")})

    branch_name = branch_name.strip()

    ok3, common_dir, _ = run_git(git_root, "rev-parse", "--git-common-dir")
    if not ok3:
        return jsonify({"ok": False, "message": t("api.error.noWorkspaceForCwd")})

    common_dir_path = Path(common_dir.strip())
    if not common_dir_path.is_absolute():
        common_dir_path = Path(git_root) / common_dir_path
    main_root = str(common_dir_path.resolve().parent)

    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE path = ?", (main_root,)).fetchone()
        if not project:
            return jsonify({"ok": False, "message": t("api.error.noWorkspaceForCwd")})

        ws = find_workspace(db, project["id"], branch_name)
        if not ws:
            return jsonify({"ok": False, "message": t("api.error.noWorkspaceForCwd")})

        existing = db.execute(
            "SELECT id FROM session_history WHERE workspace_id = ? AND session_id = ?",
            (ws["id"], session_id)
        ).fetchone()
        now = datetime.now().isoformat()
        if existing:
            db.execute(
                "UPDATE session_history SET started_at = ? WHERE id = ?",
                (now, existing["id"])
            )
        else:
            db.execute(
                "INSERT INTO session_history (workspace_id, session_id, started_at) VALUES (?, ?, ?)",
                (ws["id"], session_id, now)
            )
        db.execute("UPDATE workspaces SET session_id = ? WHERE id = ?", (session_id, ws["id"]))
        db.commit()

        ws_path = workspace_dir(project["path"], branch_name)
        return jsonify({"ok": True, "workspace": str(ws_path)})
    finally:
        db.close()
