"""Tests for project CRUD endpoints."""
import json
import pytest

from testing_utils import set_phase


def test_list_projects_empty(client):
    response = client.get("/api/projects")
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"projects": []}


def test_register_project(client, git_repo):
    response = client.post("/api/projects", json={"path": git_repo, "name": "My Repo"})
    assert response.status_code == 201
    data = response.get_json()
    assert data["name"] == "My Repo"
    assert data["path"] == git_repo
    assert "id" in data
    assert "registered" in data


def test_register_project_invalid_path(client):
    response = client.post("/api/projects", json={"path": "/nonexistent/path/abc"})
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_register_project_auto_name(client, git_repo):
    response = client.post("/api/projects", json={"path": git_repo})
    assert response.status_code == 201
    data = response.get_json()
    import os
    assert data["name"] == os.path.basename(git_repo)


def test_register_project_duplicate(client, git_repo):
    client.post("/api/projects", json={"path": git_repo, "name": "First"})
    response = client.post("/api/projects", json={"path": git_repo, "name": "Second"})
    assert response.status_code == 409
    data = response.get_json()
    assert "error" in data


def test_list_projects_after_register(client, git_repo):
    client.post("/api/projects", json={"path": git_repo, "name": "Listed Project"})
    response = client.get("/api/projects")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["projects"]) == 1
    assert data["projects"][0]["path"] == git_repo


def test_delete_project(client, project):
    response = client.delete(f"/api/projects/{project['id']}")
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"ok": True}


def test_delete_project_cascades(client, workspace):
    project_id = workspace["project_id"]
    client.delete(f"/api/projects/{project_id}")
    response = client.get(f"/api/projects/{project_id}/workspaces")
    assert response.status_code == 404
