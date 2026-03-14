"""File read and diff routes."""
from pathlib import Path

from flask import Blueprint, jsonify, request

from db import get_db
from helpers import find_workspace, run_git
from i18n import t

bp = Blueprint("files", __name__)


@bp.route("/api/ws/<project_id>/<path:branch>/file", methods=["GET"])
def read_file(project_id, branch):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        working_dir = ws["working_dir"]
    finally:
        db.close()

    rel_path = request.args.get("path", "")
    start_line = request.args.get("start", type=int)
    end_line = request.args.get("end", type=int)
    absolute = request.args.get("absolute", "").lower() in ("true", "1")

    if not rel_path:
        return jsonify({"error": t("api.error.pathRequired")}), 400

    if absolute:
        file_path = Path(rel_path)
    else:
        file_path = Path(working_dir) / rel_path
        try:
            file_path.resolve().relative_to(Path(working_dir).resolve())
        except ValueError:
            return jsonify({"error": t("api.error.pathOutsideWorkingDir")}), 403

    if not file_path.exists():
        return jsonify({"error": t("api.error.fileNotFound")}), 404

    try:
        lines = file_path.read_text().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        return jsonify({"error": str(e)}), 500

    if start_line is not None and end_line is not None:
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        context_before = max(0, start_idx - 5)
        context_after = min(len(lines), end_idx + 5)
        selected_lines = lines[context_before:context_after]
        return jsonify({
            "path": rel_path,
            "start": context_before + 1,
            "end": context_after,
            "highlight_start": start_line,
            "highlight_end": end_line,
            "lines": selected_lines,
            "total_lines": len(lines)
        })

    return jsonify({
        "path": rel_path,
        "lines": lines,
        "total_lines": len(lines)
    })


@bp.route("/api/ws/<project_id>/<path:branch>/files", methods=["GET"])
def list_files(project_id, branch):
    """List tracked files as a flat list. Uses git ls-files for accuracy."""
    db = get_db()
    try:
        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404
        working_dir = ws["working_dir"]
    finally:
        db.close()

    ok, output, _ = run_git(working_dir, "ls-files")
    if not ok:
        return jsonify({"error": t("api.error.failedToListFiles")}), 500

    files = [f for f in output.strip().split("\n") if f]
    return jsonify({"files": files})


@bp.route("/api/ws/<project_id>/<path:branch>/diff", methods=["GET"])
def get_diff(project_id, branch):
    db = get_db()
    try:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"error": t("api.error.projectNotFound")}), 404

        ws = find_workspace(db, project_id, branch)
        if not ws:
            return jsonify({"error": t("api.error.workspaceNotFound")}), 404

        working_dir = ws["working_dir"]
        source_branch = ws["source_branch"] or "develop"
    finally:
        db.close()

    mode = request.args.get("mode", "branch")
    if mode not in ("branch", "uncommitted"):
        mode = "branch"

    if mode == "uncommitted":
        ok1, unstaged_out, _ = run_git(working_dir, "diff")
        ok2, staged_out, _ = run_git(working_dir, "diff", "--cached")
        diff_output = ""
        if ok1 and unstaged_out:
            diff_output += unstaged_out
        if ok2 and staged_out:
            if diff_output:
                diff_output += "\n"
            diff_output += staged_out
    else:
        # Diff against remote source branch (local ref may be stale in worktrees)
        ok, diff_output, _ = run_git(working_dir, "diff", f"origin/{source_branch}")
        if not ok:
            ok, diff_output, _ = run_git(working_dir, "diff", source_branch)
        if not ok:
            ok, diff_output, _ = run_git(working_dir, "diff", "HEAD")
        if not ok:
            ok, diff_output, _ = run_git(working_dir, "diff")

    files = _parse_diff(diff_output)
    tracked_paths = {f["path"] for f in files}

    # Include untracked (new) files as synthetic diffs.
    # git status --porcelain shows untracked directories as "?? dirname/" instead of
    # listing individual files, so we use ls-files --others for complete coverage.
    new_paths = set()
    ok_ls, ls_out, _ = run_git(working_dir, "ls-files", "--others", "--exclude-standard")
    if ok_ls:
        new_paths.update(line.strip() for line in ls_out.splitlines() if line.strip())

    if mode == "branch":
        ok_cached, cached_out, _ = run_git(working_dir, "diff", "--cached", "--name-only")
        if ok_cached:
            new_paths.update(line.strip() for line in cached_out.splitlines() if line.strip())

    for rel_path in new_paths:
        if rel_path in tracked_paths:
            continue
        file_path = Path(working_dir) / rel_path
        try:
            content = file_path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        content_lines = content.splitlines()
        diff_lines = [
            f"diff --git a/{rel_path} b/{rel_path}",
            "new file mode 100644",
            "--- /dev/null",
            f"+++ b/{rel_path}",
            f"@@ -0,0 +1,{len(content_lines)} @@",
        ] + ["+" + l for l in content_lines]
        files.append({
            "path": rel_path,
            "additions": len(content_lines),
            "deletions": 0,
            "diff": "\n".join(diff_lines),
            "status": "new",
        })

    return jsonify({"files": files, "mode": mode})


def _parse_diff(diff_output):
    """Parse unified diff output into a list of file entries."""
    files = []
    if not diff_output or not diff_output.strip():
        return files

    current_file = None
    current_diff_lines = []

    for line in diff_output.split("\n"):
        if line.startswith("diff --git"):
            if current_file:
                files.append({
                    "path": current_file,
                    "additions": sum(1 for l in current_diff_lines if l.startswith("+") and not l.startswith("+++")),
                    "deletions": sum(1 for l in current_diff_lines if l.startswith("-") and not l.startswith("---")),
                    "diff": "\n".join(current_diff_lines)
                })
            parts = line.split(" b/", 1)
            current_file = parts[1] if len(parts) > 1 else ""
            current_diff_lines = [line]
        elif current_file is not None:
            current_diff_lines.append(line)

    if current_file:
        files.append({
            "path": current_file,
            "additions": sum(1 for l in current_diff_lines if l.startswith("+") and not l.startswith("+++")),
            "deletions": sum(1 for l in current_diff_lines if l.startswith("-") and not l.startswith("---")),
            "diff": "\n".join(current_diff_lines)
        })

    return files
