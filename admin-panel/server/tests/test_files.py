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
