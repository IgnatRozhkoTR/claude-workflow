"""Tests for session hook routes."""
from testing_utils import _git


def test_session_start_success(client, workspace):
    _git(workspace["working_dir"], "checkout", "-b", "feature/test")
    r = client.post(
        "/api/hook/session-start",
        json={"session_id": "sess-123", "cwd": workspace["working_dir"]},
    )
    assert r.status_code == 200
    assert r.json["ok"] is True

    from db import get_db
    db = get_db()
    row = db.execute(
        "SELECT session_id FROM workspaces WHERE id = ?", (workspace["id"],)
    ).fetchone()
    db.close()
    assert row["session_id"] == "sess-123"


def test_session_start_no_session_id(client):
    r = client.post("/api/hook/session-start", json={"cwd": "/tmp"})
    assert r.status_code == 400
    assert "session_id" in r.json["error"].lower()


def test_session_start_no_workspace(client, project, git_repo):
    # git_repo is on develop; no workspace registered for develop branch
    r = client.post(
        "/api/hook/session-start",
        json={"session_id": "sess-789", "cwd": git_repo},
    )
    assert r.status_code == 200
    assert r.json["ok"] is False


def test_session_start_no_git_repo(client, tmp_path):
    r = client.post(
        "/api/hook/session-start",
        json={"session_id": "sess-456", "cwd": str(tmp_path)},
    )
    assert r.status_code == 200
    assert r.json["ok"] is False


def test_session_start_records_history(client, workspace):
    _git(workspace["working_dir"], "checkout", "-b", "feature/test")

    client.post(
        "/api/hook/session-start",
        json={"session_id": "sess-first", "cwd": workspace["working_dir"]},
    )
    client.post(
        "/api/hook/session-start",
        json={"session_id": "sess-second", "cwd": workspace["working_dir"]},
    )

    from db import get_db
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM session_history WHERE workspace_id = ?", (workspace["id"],)
    ).fetchone()[0]
    db.close()
    assert count == 2


def test_session_start_deduplicates(client, workspace):
    _git(workspace["working_dir"], "checkout", "-b", "feature/test")

    client.post(
        "/api/hook/session-start",
        json={"session_id": "sess-dup", "cwd": workspace["working_dir"]},
    )
    client.post(
        "/api/hook/session-start",
        json={"session_id": "sess-dup", "cwd": workspace["working_dir"]},
    )

    from db import get_db
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM session_history WHERE workspace_id = ? AND session_id = 'sess-dup'",
        (workspace["id"],)
    ).fetchone()[0]
    db.close()
    assert count == 1
