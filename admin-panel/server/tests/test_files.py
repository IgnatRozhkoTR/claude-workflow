"""Tests for file read and diff routes."""
import os
from pathlib import Path

from testing_utils import _git


def test_read_file(client, workspace):
    Path(workspace["working_dir"]).joinpath("test.txt").write_text("line1\nline2\nline3\n")
    r = client.get("/api/ws/test-project/feature/test/file?path=test.txt")
    assert r.status_code == 200
    assert r.json["lines"] == ["line1", "line2", "line3"]
    assert r.json["path"] == "test.txt"
    assert r.json["total_lines"] == 3


def test_read_file_with_range(client, workspace):
    content = "\n".join(f"line{i}" for i in range(1, 21)) + "\n"
    Path(workspace["working_dir"]).joinpath("big.txt").write_text(content)
    r = client.get("/api/ws/test-project/feature/test/file?path=big.txt&start=8&end=12")
    assert r.status_code == 200
    data = r.json
    assert data["highlight_start"] == 8
    assert data["highlight_end"] == 12
    # context window is ±5 lines: start=max(0, 8-1-5)=2, end=min(20, 12+5)=17
    assert data["start"] == 3
    assert data["end"] == 17
    assert "line8" in data["lines"]
    assert "line12" in data["lines"]


def test_read_file_missing_path(client, workspace):
    r = client.get("/api/ws/test-project/feature/test/file")
    assert r.status_code == 400
    assert "path" in r.json["error"].lower()


def test_read_file_not_found(client, workspace):
    r = client.get("/api/ws/test-project/feature/test/file?path=nonexistent.txt")
    assert r.status_code == 404


def test_read_file_path_traversal(client, workspace):
    r = client.get("/api/ws/test-project/feature/test/file?path=../../etc/passwd")
    assert r.status_code == 403


def test_read_file_absolute_path(client, workspace):
    """Read a file using absolute path within the workspace working_dir."""
    abs_file = Path(workspace["working_dir"]) / "absolute_test.py"
    abs_file.write_text("external_code = True\n")
    r = client.get(f"/api/ws/test-project/feature/test/file?path={abs_file}&absolute=true")
    assert r.status_code == 200
    assert "external_code" in r.json["lines"][0]


def test_read_file_absolute_path_outside_workspace(client, workspace):
    """Absolute path outside workspace working_dir is blocked."""
    import tempfile
    fd, temp_path = tempfile.mkstemp(suffix=".py")
    try:
        os.write(fd, b"secret = True\n")
        os.close(fd)
        r = client.get(f"/api/ws/test-project/feature/test/file?path={temp_path}&absolute=true")
        assert r.status_code == 403
    finally:
        os.unlink(temp_path)


def test_read_file_absolute_without_flag(client, workspace):
    """Absolute-looking path without flag is still blocked."""
    r = client.get("/api/ws/test-project/feature/test/file?path=/etc/passwd")
    assert r.status_code == 403


def test_list_files(client, workspace):
    Path(workspace["working_dir"]).joinpath("hello.py").write_text("print('hi')")
    _git(workspace["working_dir"], "add", "hello.py")
    _git(workspace["working_dir"], "commit", "-m", "Add file")
    r = client.get("/api/ws/test-project/feature/test/files")
    assert r.status_code == 200
    names = [e["name"] for e in r.json["entries"]]
    assert "hello.py" in names


def test_list_files_root_has_total(client, workspace):
    Path(workspace["working_dir"]).joinpath("a.py").write_text("x = 1")
    Path(workspace["working_dir"]).joinpath("b.py").write_text("y = 2")
    _git(workspace["working_dir"], "add", "a.py", "b.py")
    _git(workspace["working_dir"], "commit", "-m", "Add files")
    r = client.get("/api/ws/test-project/feature/test/files")
    assert r.status_code == 200
    assert "total" in r.json
    assert r.json["total"] >= 2


def test_list_files_subdirectory(client, workspace):
    subdir = Path(workspace["working_dir"]) / "subpkg"
    subdir.mkdir()
    (subdir / "service.py").write_text("class Service: pass")
    (subdir / "utils.py").write_text("def helper(): pass")
    Path(workspace["working_dir"]).joinpath("root.py").write_text("x = 1")
    _git(workspace["working_dir"], "add", "subpkg/service.py", "subpkg/utils.py", "root.py")
    _git(workspace["working_dir"], "commit", "-m", "Add subdir files")
    r = client.get("/api/ws/test-project/feature/test/files?path=subpkg")
    assert r.status_code == 200
    names = [e["name"] for e in r.json["entries"]]
    assert "service.py" in names
    assert "utils.py" in names
    assert "root.py" not in names


def test_list_files_entries_have_type(client, workspace):
    subdir = Path(workspace["working_dir"]) / "mypkg"
    subdir.mkdir()
    (subdir / "module.py").write_text("pass")
    Path(workspace["working_dir"]).joinpath("main.py").write_text("pass")
    _git(workspace["working_dir"], "add", "mypkg/module.py", "main.py")
    _git(workspace["working_dir"], "commit", "-m", "Add files and dir")
    r = client.get("/api/ws/test-project/feature/test/files")
    assert r.status_code == 200
    types = {e["name"]: e["type"] for e in r.json["entries"]}
    assert types["mypkg"] == "dir"
    assert types["main.py"] == "file"


def test_list_files_dirs_sorted_first(client, workspace):
    subdir = Path(workspace["working_dir"]) / "alpha"
    subdir.mkdir()
    (subdir / "code.py").write_text("pass")
    Path(workspace["working_dir"]).joinpath("zz_file.py").write_text("pass")
    _git(workspace["working_dir"], "add", "alpha/code.py", "zz_file.py")
    _git(workspace["working_dir"], "commit", "-m", "Add dir and file")
    r = client.get("/api/ws/test-project/feature/test/files")
    assert r.status_code == 200
    entries = r.json["entries"]
    dir_indices = [i for i, e in enumerate(entries) if e["type"] == "dir"]
    file_indices = [i for i, e in enumerate(entries) if e["type"] == "file"]
    assert all(d < f for d in dir_indices for f in file_indices)


def test_list_files_search(client, workspace):
    Path(workspace["working_dir"]).joinpath("order_service.py").write_text("pass")
    Path(workspace["working_dir"]).joinpath("order_repo.py").write_text("pass")
    Path(workspace["working_dir"]).joinpath("user_service.py").write_text("pass")
    _git(workspace["working_dir"], "add", "order_service.py", "order_repo.py", "user_service.py")
    _git(workspace["working_dir"], "commit", "-m", "Add service files")
    r = client.get("/api/ws/test-project/feature/test/files?search=order")
    assert r.status_code == 200
    names = [e["name"] for e in r.json["entries"]]
    assert "order_service.py" in names
    assert "order_repo.py" in names
    assert "user_service.py" not in names


def test_list_files_search_empty(client, workspace):
    Path(workspace["working_dir"]).joinpath("readme.txt").write_text("docs")
    _git(workspace["working_dir"], "add", "readme.txt")
    _git(workspace["working_dir"], "commit", "-m", "Add readme")
    r = client.get("/api/ws/test-project/feature/test/files?search=nonexistentxyz")
    assert r.status_code == 200
    assert r.json["entries"] == []


def test_list_files_subdirectory_no_total(client, workspace):
    subdir = Path(workspace["working_dir"]) / "pkg"
    subdir.mkdir()
    (subdir / "a.py").write_text("pass")
    _git(workspace["working_dir"], "add", "pkg/a.py")
    _git(workspace["working_dir"], "commit", "-m", "Add pkg")
    r = client.get("/api/ws/test-project/feature/test/files?path=pkg")
    assert r.status_code == 200
    assert "total" not in r.json


def test_list_files_collapses_single_child_dirs(client, workspace):
    """Single-child directory chains are collapsed into one entry."""
    wd = Path(workspace["working_dir"])
    (wd / "src" / "main" / "java").mkdir(parents=True)
    (wd / "src" / "main" / "java" / "App.java").write_text("class App {}")
    _git(workspace["working_dir"], "add", "-A")
    _git(workspace["working_dir"], "commit", "-m", "deep structure")
    r = client.get("/api/ws/test-project/feature/test/files")
    assert r.status_code == 200
    dir_entries = [e for e in r.json["entries"] if e["type"] == "dir"]
    # src/main/java should be collapsed into one entry
    assert any("src/main/java" in e["name"] for e in dir_entries)
    # path should point to the deepest collapsed dir
    collapsed = [e for e in dir_entries if "src/main/java" in e["name"]][0]
    assert collapsed["path"] == "src/main/java"


def test_list_files_workspace_not_found(client, project):
    r = client.get("/api/ws/test-project/nonexistent/branch/files")
    assert r.status_code == 404


def test_get_diff_with_changes(client, workspace):
    _git(workspace["working_dir"], "checkout", "-b", "feature/test")
    Path(workspace["working_dir"]).joinpath("new.py").write_text("x = 1\n")
    _git(workspace["working_dir"], "add", "new.py")
    _git(workspace["working_dir"], "commit", "-m", "Add new.py")
    r = client.get("/api/ws/test-project/feature/test/diff")
    assert r.status_code == 200
    paths = [f["path"] for f in r.json["files"]]
    assert "new.py" in paths


def test_get_diff_no_changes(client, workspace):
    r = client.get("/api/ws/test-project/feature/test/diff")
    assert r.status_code == 200
    assert r.json["files"] == []


def test_get_diff_untracked_files(client, workspace):
    Path(workspace["working_dir"]).joinpath("untracked.py").write_text("y = 2\n")
    r = client.get("/api/ws/test-project/feature/test/diff")
    assert r.status_code == 200
    untracked = [f for f in r.json["files"] if f["path"] == "untracked.py"]
    assert len(untracked) == 1
    assert untracked[0]["status"] == "new"


def test_get_diff_untracked_files_in_new_directory(client, workspace):
    newpkg_dir = Path(workspace["working_dir"]) / "newpkg"
    newpkg_dir.mkdir()
    (newpkg_dir / "service.py").write_text("class Service:\n    pass\n")
    r = client.get("/api/ws/test-project/feature/test/diff")
    assert r.status_code == 200
    matched = [f for f in r.json["files"] if f["path"] == "newpkg/service.py"]
    assert len(matched) == 1
    assert matched[0]["status"] == "new"


def test_get_diff_uncommitted_mode(client, workspace):
    working_dir = workspace["working_dir"]
    # Create and commit a base file
    Path(working_dir).joinpath("base.py").write_text("x = 1\n")
    _git(working_dir, "add", "base.py")
    _git(working_dir, "commit", "-m", "Add base.py")
    # Stage a modification (creates staged change)
    Path(working_dir).joinpath("base.py").write_text("x = 1\ny = 2\n")
    _git(working_dir, "add", "base.py")
    # Make an unstaged modification on top
    Path(working_dir).joinpath("base.py").write_text("x = 1\ny = 2\nz = 3\n")
    r = client.get("/api/ws/test-project/feature/test/diff?mode=uncommitted")
    assert r.status_code == 200
    assert r.json["mode"] == "uncommitted"
    paths = [f["path"] for f in r.json["files"]]
    assert "base.py" in paths
    combined_diff = " ".join(f["diff"] for f in r.json["files"] if f["path"] == "base.py")
    assert "+y = 2" in combined_diff
    assert "+z = 3" in combined_diff


def test_get_diff_uncommitted_mode_untracked(client, workspace):
    Path(workspace["working_dir"]).joinpath("newfile.py").write_text("a = 42\n")
    r = client.get("/api/ws/test-project/feature/test/diff?mode=uncommitted")
    assert r.status_code == 200
    assert r.json["mode"] == "uncommitted"
    matched = [f for f in r.json["files"] if f["path"] == "newfile.py"]
    assert len(matched) == 1
    assert matched[0]["status"] == "new"


def test_get_diff_branch_mode_explicit(client, workspace):
    r = client.get("/api/ws/test-project/feature/test/diff?mode=branch")
    assert r.status_code == 200
    assert r.json["mode"] == "branch"
    assert isinstance(r.json["files"], list)


# ---------------------------------------------------------------------------
# History endpoint tests
# ---------------------------------------------------------------------------

def _make_origin_ref(working_dir, source_branch="develop"):
    """Pin origin/<source_branch> to the current HEAD so future commits are 'ahead'."""
    import subprocess
    from testing_utils import GIT_ENV
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=working_dir, capture_output=True, text=True, env=GIT_ENV
    )
    sha = result.stdout.strip()
    subprocess.run(
        ["git", "update-ref", f"refs/remotes/origin/{source_branch}", sha],
        cwd=working_dir, check=True, capture_output=True, env=GIT_ENV
    )
    return sha


def test_history_endpoint_returns_commits_for_simple_branch(client, workspace):
    wd = workspace["working_dir"]
    _make_origin_ref(wd)

    Path(wd).joinpath("a.py").write_text("x = 1\n")
    _git(wd, "add", "a.py")
    _git(wd, "commit", "-m", "First ahead commit")

    Path(wd).joinpath("b.py").write_text("y = 2\n")
    _git(wd, "add", "b.py")
    _git(wd, "commit", "-m", "Second ahead commit")

    r = client.get("/api/ws/test-project/feature/test/history")
    assert r.status_code == 200
    data = r.json
    assert data["source_branch"] == "develop"
    assert len(data["commits"]) == 2
    subjects = [c["subject"] for c in data["commits"]]
    assert "First ahead commit" in subjects
    assert "Second ahead commit" in subjects
    for commit in data["commits"]:
        assert commit["ahead_of_origin"] is True
        assert len(commit["sha"]) == 12
        assert len(commit["full_sha"]) == 40
        assert commit["author_name"] == "Test"
        assert commit["author_email"] == "test@test.com"
        assert commit["author_date"]


def test_history_endpoint_empty_when_no_new_commits(client, workspace):
    wd = workspace["working_dir"]
    _make_origin_ref(wd)

    r = client.get("/api/ws/test-project/feature/test/history")
    assert r.status_code == 200
    data = r.json
    assert data["commits"] == []
    assert data["source_branch"] == "develop"


def test_history_endpoint_handles_commit_with_special_chars(client, workspace):
    wd = workspace["working_dir"]
    _make_origin_ref(wd)

    Path(wd).joinpath("c.py").write_text("pass\n")
    _git(wd, "add", "c.py")
    import subprocess
    from testing_utils import GIT_ENV
    subprocess.run(
        ["git", "commit", "-m", 'Subject with "quotes"', "-m", "Body line one\nBody line two"],
        cwd=wd, check=True, capture_output=True, env=GIT_ENV
    )

    r = client.get("/api/ws/test-project/feature/test/history")
    assert r.status_code == 200
    commits = r.json["commits"]
    assert len(commits) == 1
    c = commits[0]
    assert '"quotes"' in c["subject"]
    assert c["body"]


# ---------------------------------------------------------------------------
# Diff mode=commit tests
# ---------------------------------------------------------------------------

def _commit_file(working_dir, filename, content, message):
    """Create, stage and commit a file; return the full SHA."""
    import subprocess
    from testing_utils import GIT_ENV
    Path(working_dir).joinpath(filename).write_text(content)
    _git(working_dir, "add", filename)
    _git(working_dir, "commit", "-m", message)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=working_dir, capture_output=True, text=True, env=GIT_ENV
    )
    return result.stdout.strip()


def test_diff_mode_commit_returns_commit_diff(client, workspace):
    wd = workspace["working_dir"]
    _commit_file(wd, "first.py", "a = 1\n", "First commit")
    sha2 = _commit_file(wd, "second.py", "b = 2\n", "Second commit")

    r = client.get(f"/api/ws/test-project/feature/test/diff?mode=commit&commit={sha2}")
    assert r.status_code == 200
    data = r.json
    assert data["mode"] == "commit"
    assert data["commit"] == sha2
    paths = [f["path"] for f in data["files"]]
    assert "second.py" in paths
    assert "first.py" not in paths


def test_diff_mode_commit_missing_sha_returns_400(client, workspace):
    r = client.get("/api/ws/test-project/feature/test/diff?mode=commit")
    assert r.status_code == 400
    assert "commit" in r.json["error"].lower()


def test_diff_mode_commit_unknown_sha_returns_404(client, workspace):
    r = client.get("/api/ws/test-project/feature/test/diff?mode=commit&commit=deadbeef1234")
    assert r.status_code == 404


def test_diff_mode_commit_not_in_history_returns_400(client, workspace, tmp_path):
    wd = workspace["working_dir"]

    # Create a separate repo with a commit that is not an ancestor of wd HEAD.
    other_repo = tmp_path / "other"
    other_repo.mkdir()
    import subprocess
    from testing_utils import GIT_ENV
    subprocess.run(["git", "init"], cwd=str(other_repo), check=True, capture_output=True, env=GIT_ENV)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "Orphan commit"],
        cwd=str(other_repo), check=True, capture_output=True, env=GIT_ENV
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(other_repo), capture_output=True, text=True, env=GIT_ENV
    )
    orphan_sha = result.stdout.strip()

    # Fetch the orphan commit object into wd using git fetch.
    subprocess.run(
        ["git", "fetch", str(other_repo), "HEAD"],
        cwd=wd, check=True, capture_output=True, env=GIT_ENV
    )

    r = client.get(f"/api/ws/test-project/feature/test/diff?mode=commit&commit={orphan_sha}")
    assert r.status_code == 400
    assert "ancestor" in r.json["error"].lower()


def test_diff_mode_branch_still_works(client, workspace):
    wd = workspace["working_dir"]
    # Pin origin/develop before adding the commit so the new file appears in diff.
    _make_origin_ref(wd)
    _commit_file(wd, "branch_file.py", "z = 99\n", "Branch commit")

    r = client.get("/api/ws/test-project/feature/test/diff?mode=branch")
    assert r.status_code == 200
    data = r.json
    assert data["mode"] == "branch"
    paths = [f["path"] for f in data["files"]]
    assert "branch_file.py" in paths


def test_diff_mode_uncommitted_still_works(client, workspace):
    wd = workspace["working_dir"]
    Path(wd).joinpath("staged.py").write_text("s = 1\n")
    _git(wd, "add", "staged.py")

    r = client.get("/api/ws/test-project/feature/test/diff?mode=uncommitted")
    assert r.status_code == 200
    data = r.json
    assert data["mode"] == "uncommitted"
    paths = [f["path"] for f in data["files"]]
    assert "staged.py" in paths


def test_diff_mode_commit_does_not_include_untracked(client, workspace):
    wd = workspace["working_dir"]
    sha = _commit_file(wd, "tracked.py", "t = 1\n", "Tracked commit")

    # Add an untracked file that should NOT appear in commit mode.
    Path(wd).joinpath("untracked_extra.py").write_text("u = 99\n")

    r = client.get(f"/api/ws/test-project/feature/test/diff?mode=commit&commit={sha}")
    assert r.status_code == 200
    paths = [f["path"] for f in r.json["files"]]
    assert "tracked.py" in paths
    assert "untracked_extra.py" not in paths
