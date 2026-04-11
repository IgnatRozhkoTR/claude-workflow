"""File read and diff routes."""
from pathlib import Path

from flask import Blueprint, jsonify, request

from core.decorators import with_workspace
from core.helpers import run_git, DEFAULT_SOURCE_BRANCH
from core.i18n import t

bp = Blueprint("files", __name__)


def _is_within(path: Path, root: Path) -> bool:
    """Return True if path is within root (both resolved)."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@bp.route("/api/ws/<project_id>/<path:branch>/file", methods=["GET"])
@with_workspace
def read_file(db, ws, project):
    working_dir = ws["working_dir"]

    rel_path = request.args.get("path", "")
    start_line = request.args.get("start", type=int)
    end_line = request.args.get("end", type=int)
    absolute = request.args.get("absolute", "").lower() in ("true", "1")

    if not rel_path:
        return jsonify({"error": t("api.error.pathRequired")}), 400

    if absolute:
        file_path = Path(rel_path).resolve()
        allowed_roots = [Path(working_dir).resolve()]
        allowed_external = ws["allowed_external_paths"] if ws["allowed_external_paths"] else ""
        for ext_path in (p.strip() for p in allowed_external.split(",") if p.strip()):
            allowed_roots.append(Path(ext_path).resolve())
        if not any(_is_within(file_path, root) for root in allowed_roots):
            return jsonify({"error": t("api.error.pathOutsideWorkingDir")}), 403
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


def _collapse_single_dirs(entries, all_files):
    """Collapse chains of directories that contain only a single subdirectory."""
    result = []
    for entry in entries:
        if entry["type"] != "dir":
            result.append(entry)
            continue

        dir_path = entry["path"]
        display_name = entry["name"]

        while True:
            prefix = dir_path + "/"
            children = {}
            for f in all_files:
                if not f.startswith(prefix):
                    continue
                relative = f[len(prefix):]
                first_part = relative.split("/")[0]
                is_dir = "/" in relative
                if first_part not in children:
                    children[first_part] = is_dir

            dir_children = {k: v for k, v in children.items() if v}
            file_children = {k: v for k, v in children.items() if not v}

            if len(dir_children) == 1 and len(file_children) == 0:
                only_child = list(dir_children.keys())[0]
                display_name += "/" + only_child
                dir_path = dir_path + "/" + only_child
            else:
                break

        result.append({"name": display_name, "type": "dir", "path": dir_path})
    return result


@bp.route("/api/ws/<project_id>/<path:branch>/files", methods=["GET"])
@with_workspace
def list_files(db, ws, project):
    """List directory entries lazily. Returns one level of entries at a time."""
    working_dir = ws["working_dir"]

    dir_path = request.args.get("path", "")
    search = request.args.get("search", "").strip().lower()

    ok, output, _ = run_git(working_dir, "ls-files")
    if not ok:
        return jsonify({"error": t("api.error.failedToListFiles")}), 500

    all_files = [f for f in output.strip().split("\n") if f]

    if search:
        matched = [f for f in all_files if search in f.split("/")[-1].lower()]
        return jsonify({"entries": [{"name": f, "path": f, "type": "file"} for f in matched[:200]]})

    if dir_path:
        prefix = dir_path.rstrip("/") + "/"
        children_files = [f for f in all_files if f.startswith(prefix)]
    else:
        prefix = ""
        children_files = all_files

    entries = {}
    for f in children_files:
        relative = f[len(prefix):]
        first_part = relative.split("/")[0]
        is_dir = "/" in relative
        if first_part not in entries:
            entries[first_part] = {"name": first_part, "type": "dir" if is_dir else "file", "path": (prefix + first_part) if is_dir else f}

    sorted_entries = sorted(entries.values(), key=lambda e: (0 if e["type"] == "dir" else 1, e["name"].lower()))
    sorted_entries = _collapse_single_dirs(sorted_entries, all_files)

    result = {"entries": sorted_entries}
    if not dir_path:
        result["total"] = len(all_files)
    return jsonify(result)


_LOG_FORMAT = "%H%x00%h%x00%s%x00%an%x00%ae%x00%aI%x00%b%x1e"


def _parse_log(raw, ahead_shas):
    commits = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split("\x00", 6)
        if len(parts) < 6:
            continue
        full_sha = parts[0]
        sha = parts[1]
        subject = parts[2]
        author_name = parts[3]
        author_email = parts[4]
        author_date = parts[5]
        body = parts[6].strip() if len(parts) > 6 else ""
        commits.append({
            "sha": sha,
            "full_sha": full_sha,
            "subject": subject,
            "body": body,
            "author_name": author_name,
            "author_email": author_email,
            "author_date": author_date,
            "ahead_of_origin": full_sha in ahead_shas,
        })
    return commits


def _ahead_shas(working_dir, ref):
    ok, out, _ = run_git(working_dir, "log", "--pretty=format:%H", f"{ref}..HEAD")
    if not ok:
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def _try_history_refs(working_dir, source_branch, log_format):
    """Try candidate ref expressions in order; return (raw_log, ahead_shas_set) for the first success."""
    candidates = [
        f"origin/{source_branch}..HEAD",
        f"{source_branch}..HEAD",
        None,
    ]
    for ref_expr in candidates:
        if ref_expr is not None:
            ok, raw, _ = run_git(working_dir, "log", "--abbrev=12", f"--format={log_format}", ref_expr)
            if ok:
                ahead = _ahead_shas(working_dir, ref_expr.split("..")[0])
                return raw, ahead
        else:
            ok, raw, _ = run_git(working_dir, "log", "--abbrev=12", f"--format={log_format}", "--max-count=200")
            if not ok:
                return "", set()
            ok_rev, out_rev, _ = run_git(working_dir, "rev-list", "--max-count=200", "HEAD")
            all_shas = {line.strip() for line in out_rev.splitlines() if line.strip()} if ok_rev else set()
            return raw, all_shas
    return "", set()


@bp.route("/api/ws/<project_id>/<path:branch>/history", methods=["GET"])
@with_workspace
def get_history(db, ws, project):
    working_dir = ws["working_dir"]

    ref_param = request.args.get("ref")
    if ref_param:
        ok, raw, _ = run_git(working_dir, "log", "--abbrev=12", f"--format={_LOG_FORMAT}", "--max-count=50", ref_param)
        if not ok:
            return jsonify({"commits": [], "source_branch": ref_param})
        commits = _parse_log(raw, set())
        return jsonify({"commits": commits, "source_branch": ref_param, "browsing": True})

    source_branch = ws["source_branch"] or DEFAULT_SOURCE_BRANCH
    raw, ahead = _try_history_refs(working_dir, source_branch, _LOG_FORMAT)
    commits = _parse_log(raw, ahead)
    return jsonify({"commits": commits, "source_branch": source_branch})


@bp.route("/api/ws/<project_id>/<path:branch>/branches", methods=["GET"])
@with_workspace
def get_branches(db, ws, project):
    working_dir = ws["working_dir"]
    ok, out, _ = run_git(working_dir, "branch", "-a", "--sort=-committerdate", "--format=%(refname:short)")
    if not ok:
        return jsonify({"branches": []})

    current_branch = ws["branch"] or ""
    branches = []
    seen = set()
    for line in out.splitlines():
        name = line.strip()
        if not name or name == "HEAD" or "HEAD ->" in name:
            continue
        display_name = name
        if name.startswith("origin/"):
            display_name = name[7:]
            if display_name == "HEAD":
                continue
        if display_name in seen:
            continue
        seen.add(display_name)
        branches.append({
            "name": display_name,
            "ref": name,
            "current": display_name == current_branch,
        })
    return jsonify({"branches": branches})


def _diff_for_commit(working_dir, sha):
    """Validate sha and return parsed diff files list, or an error tuple."""
    if not sha:
        return jsonify({"error": "commit query parameter is required for mode=commit"}), 400

    ok_cat, _, _ = run_git(working_dir, "cat-file", "-e", f"{sha}^{{commit}}")
    if not ok_cat:
        return jsonify({"error": "commit not found"}), 404

    ok, diff_output, _ = run_git(working_dir, "show", "--format=", "--patch", sha)
    return _parse_diff(diff_output if ok else "")


def _diff_for_branch(working_dir, source_branch):
    """Return diff output against the source branch, trying origin first then local fallbacks."""
    for ref in (f"origin/{source_branch}", source_branch, "HEAD", None):
        if ref is not None:
            ok, diff_output, _ = run_git(working_dir, "diff", ref)
        else:
            ok, diff_output, _ = run_git(working_dir, "diff")
        if ok:
            return diff_output
    return ""


def _untracked_files_diff(working_dir, mode, tracked_paths):
    """Return synthetic diff entries for untracked (new) files not already in tracked_paths."""
    new_paths = set()
    ok_ls, ls_out, _ = run_git(working_dir, "ls-files", "--others", "--exclude-standard")
    if ok_ls:
        new_paths.update(line.strip() for line in ls_out.splitlines() if line.strip())

    if mode == "branch":
        # Also include staged new files not yet in the tracked diff
        ok_cached, cached_out, _ = run_git(working_dir, "diff", "--cached", "--name-only")
        if ok_cached:
            new_paths.update(line.strip() for line in cached_out.splitlines() if line.strip())

    entries = []
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
        entries.append({
            "path": rel_path,
            "additions": len(content_lines),
            "deletions": 0,
            "diff": "\n".join(diff_lines),
            "status": "new",
        })
    return entries


@bp.route("/api/ws/<project_id>/<path:branch>/diff", methods=["GET"])
@with_workspace
def get_diff(db, ws, project):
    working_dir = ws["working_dir"]
    source_branch = ws["source_branch"] or DEFAULT_SOURCE_BRANCH

    mode = request.args.get("mode", "branch")
    if mode not in ("branch", "uncommitted", "commit"):
        return jsonify({"error": f"unknown mode '{mode}', expected: branch, uncommitted, commit"}), 400

    if mode == "commit":
        sha = request.args.get("commit", "").strip()
        result = _diff_for_commit(working_dir, sha)
        if isinstance(result, tuple):
            return result
        return jsonify({"files": result, "mode": "commit", "commit": sha})

    if mode == "branch":
        diff_output = _diff_for_branch(working_dir, source_branch)
    else:
        ok, diff_output, _ = run_git(working_dir, "diff", "HEAD")
        if not ok:
            diff_output = ""

    files = _parse_diff(diff_output)
    files.extend(_untracked_files_diff(working_dir, mode, {f["path"] for f in files}))
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
