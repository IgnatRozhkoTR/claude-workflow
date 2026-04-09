"""Integration tests for commit history mutation endpoints (rename, undo, squash)."""
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from testing_utils import GIT_ENV, _git


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rev_parse(repo, ref="HEAD"):
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=str(repo), capture_output=True, text=True, env=GIT_ENV
    )
    return result.stdout.strip()


def _log_subject(repo, ref="HEAD"):
    result = subprocess.run(
        ["git", "log", "-1", "--format=%s", ref],
        cwd=str(repo), capture_output=True, text=True, env=GIT_ENV
    )
    return result.stdout.strip()


def _commit_file(repo, filename, content, message):
    path = Path(repo) / filename
    path.write_text(content)
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)
    return _rev_parse(repo)


def _set_origin_ref(repo, source_branch="develop"):
    """Pin refs/remotes/origin/<source_branch> to current HEAD."""
    sha = _rev_parse(repo)
    subprocess.run(
        ["git", "update-ref", f"refs/remotes/origin/{source_branch}", sha],
        cwd=str(repo), check=True, capture_output=True, env=GIT_ENV
    )
    return sha


@pytest.fixture
def history_repo(tmp_path):
    """Real git repo with a bare origin, 3 pushed commits, and 3 local commits.

    Layout:
        bare_origin/ — bare repo acting as origin
        repo/        — working repo with remote 'origin' pointing at bare_origin

    Pushed commits: pushed-1, pushed-2, pushed-3  (on develop)
    Local commits:  local-1, local-2, local-3      (ahead of origin/develop)
    """
    bare = tmp_path / "bare_origin"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare"], cwd=str(bare), check=True, capture_output=True, env=GIT_ENV)

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "develop")
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=str(repo), check=True, capture_output=True, env=GIT_ENV
    )

    # 3 pushed commits
    for i in range(1, 4):
        _commit_file(repo, f"pushed_{i}.py", f"x = {i}\n", f"pushed-{i}")

    subprocess.run(
        ["git", "push", "-u", "origin", "develop"],
        cwd=str(repo), check=True, capture_output=True, env=GIT_ENV
    )

    # 3 local-only commits
    for i in range(1, 4):
        _commit_file(repo, f"local_{i}.py", f"y = {i}\n", f"local-{i}")

    return repo


@pytest.fixture
def history_workspace(history_repo, clean_db):
    """Register history_repo as a project + workspace in the test DB."""
    from core.db import get_db
    db = get_db()
    now = datetime.now().isoformat()
    project_id = "hist-project"
    db.execute(
        "INSERT INTO projects (id, name, path, registered) VALUES (?, ?, ?, ?)",
        (project_id, "Hist Project", str(history_repo), now)
    )
    cursor = db.execute(
        "INSERT INTO workspaces (project_id, branch, sanitized_branch, working_dir, "
        "created, status, phase, scope_json, plan_json, source_branch) "
        "VALUES (?, ?, ?, ?, ?, 'active', '0', ?, ?, ?)",
        (
            project_id, "develop", "develop", str(history_repo),
            now, '{"must":[],"may":[]}',
            '{"description":"","systemDiagram":"","execution":[]}', "develop"
        )
    )
    ws_id = cursor.lastrowid
    db.commit()
    db.close()
    return {
        "id": ws_id,
        "project_id": project_id,
        "branch": "develop",
        "working_dir": str(history_repo),
    }


# ---------------------------------------------------------------------------
# Rename tests
# ---------------------------------------------------------------------------

def test_rename_happy_path(client, history_workspace):
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]

    r = client.post(
        f"/api/ws/{pid}/develop/history/rename",
        json={"message": "renamed-local-3"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["subject"] == "renamed-local-3"
    assert _log_subject(repo) == "renamed-local-3"


def test_rename_rejects_pushed_head(client, history_workspace, tmp_path):
    """If we check out a pushed commit (detach HEAD to a pushed SHA) the branch
    check fires first. Instead, simulate by temporarily moving origin ref forward
    to equal HEAD so HEAD is 'pushed'."""
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]

    # Move origin/develop to current HEAD so the head commit is no longer ahead
    _set_origin_ref(repo, "develop")

    r = client.post(
        f"/api/ws/{pid}/develop/history/rename",
        json={"message": "should fail"},
    )
    assert r.status_code == 400
    assert "pushed" in r.get_json()["error"].lower()


def test_rename_rejects_dirty_tree(client, history_workspace):
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]

    # Create an untracked file that is tracked-by-scope would appear in `git status`
    # Actually use a modified tracked file so git status --porcelain shows output
    pushed_file = Path(repo) / "pushed_1.py"
    pushed_file.write_text("modified content\n")

    r = client.post(
        f"/api/ws/{pid}/develop/history/rename",
        json={"message": "should fail"},
    )
    assert r.status_code == 400
    assert "clean" in r.get_json()["error"].lower()

    # restore
    pushed_file.write_text("x = 1\n")


def test_rename_rejects_detached_head(client, history_workspace):
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]

    sha = _rev_parse(repo)
    subprocess.run(
        ["git", "checkout", "--detach", sha],
        cwd=str(repo), check=True, capture_output=True, env=GIT_ENV
    )

    try:
        r = client.post(
            f"/api/ws/{pid}/develop/history/rename",
            json={"message": "should fail"},
        )
        assert r.status_code == 400
        error = r.get_json()["error"].lower()
        assert "detached" in error or "expected" in error
    finally:
        _git(repo, "checkout", "develop")


def test_rename_rejects_empty_message(client, history_workspace):
    pid = history_workspace["project_id"]
    r = client.post(
        f"/api/ws/{pid}/develop/history/rename",
        json={"message": ""},
    )
    assert r.status_code == 400
    assert "message" in r.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Undo tests
# ---------------------------------------------------------------------------

def test_undo_happy_path(client, history_workspace):
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]

    head_before = _rev_parse(repo)
    parent_before = _rev_parse(repo, "HEAD~1")

    r = client.post(f"/api/ws/{pid}/develop/history/undo")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["reset_to"] == parent_before

    # HEAD should now be the previous parent
    assert _rev_parse(repo) == parent_before

    # The changes from undone commit should be staged
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo), capture_output=True, text=True, env=GIT_ENV
    ).stdout
    assert status.strip()  # something staged


def test_undo_rejects_pushed_head(client, history_workspace):
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]

    _set_origin_ref(repo, "develop")

    r = client.post(f"/api/ws/{pid}/develop/history/undo")
    assert r.status_code == 400
    assert "pushed" in r.get_json()["error"].lower()


def test_undo_rejects_dirty_tree(client, history_workspace):
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]

    Path(repo, "pushed_1.py").write_text("dirty\n")
    r = client.post(f"/api/ws/{pid}/develop/history/undo")
    assert r.status_code == 400
    assert "clean" in r.get_json()["error"].lower()

    Path(repo, "pushed_1.py").write_text("x = 1\n")


def test_undo_rejects_initial_commit(client, tmp_path, clean_db):
    """A repo with a single local-unpushed commit that has no parent must reject undo.

    To satisfy _require_head_unpushed, origin/main must exist but point at an
    unrelated SHA so that origin/main..HEAD includes our orphan commit.
    """
    # Bare origin with its own unrelated commit (different history)
    bare = tmp_path / "bare_single"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare"], cwd=str(bare), check=True, capture_output=True, env=GIT_ENV)

    repo = tmp_path / "single"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=str(repo), check=True, capture_output=True, env=GIT_ENV
    )

    # Seed the bare origin with an unrelated commit (so origin/main exists)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init")
    _git(seed, "checkout", "-b", "main")
    _commit_file(seed, "seed.py", "s = 0\n", "seed-commit")
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=str(seed), check=True, capture_output=True, env=GIT_ENV
    )
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=str(seed), check=True, capture_output=True, env=GIT_ENV
    )

    # Fetch origin into our repo so origin/main exists (pointing at seed commit)
    subprocess.run(
        ["git", "fetch", "origin"],
        cwd=str(repo), check=True, capture_output=True, env=GIT_ENV
    )

    # Now make the single orphan commit on main (unrelated history)
    _commit_file(repo, "init.py", "x = 1\n", "initial commit")
    # origin/main..HEAD now includes our orphan commit (unrelated histories)

    from core.db import get_db
    db = get_db()
    now = datetime.now().isoformat()
    project_id = "single-project"
    db.execute(
        "INSERT INTO projects (id, name, path, registered) VALUES (?, ?, ?, ?)",
        (project_id, "Single", str(repo), now)
    )
    db.execute(
        "INSERT INTO workspaces (project_id, branch, sanitized_branch, working_dir, "
        "created, status, phase, scope_json, plan_json, source_branch) "
        "VALUES (?, ?, ?, ?, ?, 'active', '0', ?, ?, ?)",
        (
            project_id, "main", "main", str(repo), now,
            '{"must":[],"may":[]}',
            '{"description":"","systemDiagram":"","execution":[]}', "main"
        )
    )
    db.commit()
    db.close()

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.post(f"/api/ws/{project_id}/main/history/undo")
    assert r.status_code == 400
    assert "initial" in r.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Squash tests
# ---------------------------------------------------------------------------

def _local_shas(repo, source_branch="develop"):
    """Return all local-unpushed SHAs in log order (newest first)."""
    result = subprocess.run(
        ["git", "log", f"origin/{source_branch}..HEAD", "--format=%H"],
        cwd=str(repo), capture_output=True, text=True, env=GIT_ENV
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def test_squash_happy_path(client, history_workspace):
    """Squash the top 2 local commits."""
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]
    shas = _local_shas(repo)
    top2 = shas[:2]

    r = client.post(
        f"/api/ws/{pid}/develop/history/squash",
        json={"commits": top2, "message": "squashed-top-2"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["subject"] == "squashed-top-2"
    assert data["squashed"] == 2
    assert _log_subject(repo) == "squashed-top-2"

    remaining = _local_shas(repo)
    assert len(remaining) == 2  # was 3, now 2 (3rd local commit + new squash)


def test_squash_happy_path_three_commits(client, history_workspace):
    """Squash all 3 local commits into one."""
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]
    shas = _local_shas(repo)
    assert len(shas) == 3

    r = client.post(
        f"/api/ws/{pid}/develop/history/squash",
        json={"commits": shas, "message": "all-three-squashed"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["squashed"] == 3
    assert _log_subject(repo) == "all-three-squashed"

    remaining = _local_shas(repo)
    assert len(remaining) == 1


def test_squash_rejects_single_commit(client, history_workspace):
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]
    shas = _local_shas(repo)

    r = client.post(
        f"/api/ws/{pid}/develop/history/squash",
        json={"commits": [shas[0]], "message": "one commit"},
    )
    assert r.status_code == 400
    assert "2" in r.get_json()["error"]


def test_squash_rejects_non_contiguous(client, history_workspace):
    """Select 1st and 3rd local commits, skipping 2nd — must be rejected."""
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]
    shas = _local_shas(repo)
    assert len(shas) == 3
    non_contiguous = [shas[0], shas[2]]  # skip shas[1]

    r = client.post(
        f"/api/ws/{pid}/develop/history/squash",
        json={"commits": non_contiguous, "message": "gap"},
    )
    assert r.status_code == 400
    assert "contiguous" in r.get_json()["error"].lower()


def test_squash_rejects_pushed_commit(client, history_workspace):
    """Including a pushed commit in selection must be rejected."""
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]
    shas = _local_shas(repo)

    # Get the pushed HEAD (one commit behind the local stack)
    pushed_head = _rev_parse(repo, "origin/develop")

    r = client.post(
        f"/api/ws/{pid}/develop/history/squash",
        json={"commits": [shas[0], pushed_head], "message": "mixing pushed"},
    )
    assert r.status_code == 400
    assert "pushed" in r.get_json()["error"].lower()


def test_squash_rejects_dirty_tree(client, history_workspace):
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]
    shas = _local_shas(repo)

    Path(repo, "pushed_1.py").write_text("dirty\n")
    r = client.post(
        f"/api/ws/{pid}/develop/history/squash",
        json={"commits": shas[:2], "message": "clean first"},
    )
    assert r.status_code == 400
    assert "clean" in r.get_json()["error"].lower()

    Path(repo, "pushed_1.py").write_text("x = 1\n")


def test_squash_rejects_empty_message(client, history_workspace):
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]
    shas = _local_shas(repo)

    r = client.post(
        f"/api/ws/{pid}/develop/history/squash",
        json={"commits": shas[:2], "message": ""},
    )
    assert r.status_code == 400
    assert "message" in r.get_json()["error"].lower()


def test_squash_rejects_selection_not_including_head(client, history_workspace):
    """Squashing a contiguous range that excludes HEAD must be rejected.

    ahead_list = [C3, C2, C1]. Selecting [C2, C1] is contiguous but omits C3
    (HEAD). The reset would silently discard C3.
    """
    repo = history_workspace["working_dir"]
    pid = history_workspace["project_id"]
    shas = _local_shas(repo)
    assert len(shas) == 3  # [C3(HEAD), C2, C1]

    # Select bottom two — contiguous but excludes HEAD (shas[0])
    bottom_two = shas[1:]  # [C2, C1]

    r = client.post(
        f"/api/ws/{pid}/develop/history/squash",
        json={"commits": bottom_two, "message": "bottom squash"},
    )
    assert r.status_code == 400
    error = r.get_json()["error"].lower()
    assert "head" in error


def test_squash_rejects_when_no_origin_ref(client, tmp_path, clean_db):
    """When origin ref is absent and no local fallback ref exists, no commits are
    considered unpushed. All mutation endpoints must be rejected (fail-closed)."""
    repo = tmp_path / "noorigin"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "feature")
    _commit_file(repo, "a.py", "x = 1\n", "commit-a")
    _commit_file(repo, "b.py", "y = 2\n", "commit-b")
    # No remote, no origin/feature ref, no local 'feature' ref to compare against
    # (we ARE on feature, so feature..HEAD yields nothing — empty set)

    from core.db import get_db
    db = get_db()
    now = datetime.now().isoformat()
    project_id = "noorigin-project"
    db.execute(
        "INSERT INTO projects (id, name, path, registered) VALUES (?, ?, ?, ?)",
        (project_id, "NoOrigin", str(repo), now)
    )
    db.execute(
        "INSERT INTO workspaces (project_id, branch, sanitized_branch, working_dir, "
        "created, status, phase, scope_json, plan_json, source_branch) "
        "VALUES (?, ?, ?, ?, ?, 'active', '0', ?, ?, ?)",
        (
            project_id, "feature", "feature", str(repo), now,
            '{"must":[],"may":[]}',
            '{"description":"","systemDiagram":"","execution":[]}', "develop"
        )
    )
    db.commit()
    db.close()

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.post(
            f"/api/ws/{project_id}/feature/history/rename",
            json={"message": "should be blocked"},
        )
    assert r.status_code == 400
    assert "pushed" in r.get_json()["error"].lower()


def test_ahead_of_origin_shas_uses_local_ref_fallback(tmp_path):
    """When origin/<branch> doesn't exist but a local ref does, commits between
    the local ref and HEAD are returned (not all reachable commits)."""
    import subprocess
    from routes.history import _ahead_of_origin_shas

    repo = tmp_path / "localfb"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "develop")
    _commit_file(repo, "base.py", "x = 0\n", "base")

    # Create a local 'develop' ref pointing at the base commit,
    # then make HEAD advance beyond it on a new branch
    base_sha = _rev_parse(repo)
    _git(repo, "checkout", "-b", "feature")
    _commit_file(repo, "feat.py", "y = 1\n", "feat-commit")
    feat_sha = _rev_parse(repo)

    # No origin/feature, but local 'develop' exists as the base
    result = _ahead_of_origin_shas(str(repo), "develop")
    assert feat_sha in result
    assert base_sha not in result
