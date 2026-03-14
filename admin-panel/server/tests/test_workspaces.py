from testing_utils import _git


def test_list_branches(client, project):
    r = client.get(f"/api/projects/{project['id']}/branches")
    assert r.status_code == 200
    assert "develop" in r.json["local"]


def test_list_branches_not_found(client):
    r = client.get("/api/projects/nonexistent/branches")
    assert r.status_code == 404


def test_list_workspaces_empty(client, project):
    r = client.get(f"/api/projects/{project['id']}/workspaces")
    assert r.status_code == 200
    assert r.json["workspaces"] == []


def test_create_workspace(client, project):
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/new-ws", "source": "develop", "worktree": True},
    )
    assert r.status_code == 201
    assert r.json["branch"] == "feature/new-ws"


def test_create_workspace_no_worktree(client, project):
    _git(project["path"], "checkout", "-b", "other-branch")
    _git(project["path"], "checkout", "develop")
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "other-branch", "source": "develop", "worktree": False},
    )
    assert r.status_code in (201, 409)


def test_create_workspace_missing_branch(client, project):
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"source": "develop"},
    )
    assert r.status_code == 400


def test_create_workspace_missing_source(client, project):
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/test-src", "source": "nonexistent-branch"},
    )
    assert r.status_code == 404


def test_create_workspace_duplicate(client, project):
    client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/dup", "source": "develop", "worktree": True},
    )
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/dup", "source": "develop", "worktree": True},
    )
    assert r.status_code == 409


def test_list_workspaces_after_create(client, project):
    client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/listed", "source": "develop", "worktree": True},
    )
    r = client.get(f"/api/projects/{project['id']}/workspaces")
    assert r.status_code == 200
    assert len(r.json["workspaces"]) >= 1


def test_archive_workspace(client, workspace, project):
    r = client.put(f"/api/ws/{project['id']}/feature/test/archive")
    assert r.status_code == 200
    assert r.json["status"] == "archived"


def test_archive_workspace_not_found(client, project):
    r = client.put(f"/api/ws/{project['id']}/nonexistent/archive")
    assert r.status_code == 404


def test_archive_workspace_already_archived(client, workspace, project):
    client.put(f"/api/ws/{project['id']}/feature/test/archive")
    r = client.put(f"/api/ws/{project['id']}/feature/test/archive")
    # After archiving, sanitized_branch gains a timestamp suffix so the second
    # lookup by the original branch name finds no active workspace.
    assert r.status_code == 404
