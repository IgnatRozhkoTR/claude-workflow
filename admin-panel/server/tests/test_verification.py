"""Tests for verification profile API endpoints."""
import pytest


SYSTEM_PROFILE_NAMES = {"Java (Gradle)", "Java (Maven)", "Python", "TypeScript"}
REQUIRED_PROFILE_KEYS = {"id", "name", "language", "description", "origin", "steps"}


# ---------------------------------------------------------------------------
# Global profile endpoints
# ---------------------------------------------------------------------------

def test_list_profiles_has_system_profiles(client):
    """System profiles (Java Gradle, Java Maven, Python, TypeScript) are seeded."""
    response = client.get("/api/verification/profiles")
    assert response.status_code == 200
    data = response.get_json()
    names = {p["name"] for p in data["profiles"]}
    assert SYSTEM_PROFILE_NAMES.issubset(names)


def test_list_profiles_structure(client):
    """Each profile has id, name, language, description, origin, steps."""
    response = client.get("/api/verification/profiles")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["profiles"]) >= 4
    for profile in data["profiles"]:
        assert REQUIRED_PROFILE_KEYS.issubset(profile.keys())
        assert isinstance(profile["steps"], list)


def test_create_profile(client):
    """POST creates a new user profile."""
    response = client.post("/api/verification/profiles", json={
        "name": "My Custom Profile",
        "language": "kotlin",
        "description": "Custom Kotlin checks",
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert "id" in data

    profiles_response = client.get("/api/verification/profiles")
    profiles = profiles_response.get_json()["profiles"]
    names = [p["name"] for p in profiles]
    assert "My Custom Profile" in names


def test_create_profile_missing_name_returns_400(client):
    """POST without name returns 400."""
    response = client.post("/api/verification/profiles", json={"language": "kotlin"})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_create_profile_missing_language_returns_400(client):
    """POST without language returns 400."""
    response = client.post("/api/verification/profiles", json={"name": "No Lang"})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_create_profile_with_steps(client):
    """Create profile then add a step; step appears in profile listing."""
    create_response = client.post("/api/verification/profiles", json={
        "name": "Go Profile",
        "language": "go",
    })
    assert create_response.status_code == 200
    profile_id = create_response.get_json()["id"]

    step_response = client.post(f"/api/verification/profiles/{profile_id}/steps", json={
        "name": "Build",
        "command": "go build ./...",
        "description": "Compile Go sources",
        "timeout": 60,
    })
    assert step_response.status_code == 200
    step_data = step_response.get_json()
    assert step_data["ok"] is True
    assert "id" in step_data

    profiles_response = client.get("/api/verification/profiles")
    profiles = profiles_response.get_json()["profiles"]
    go_profile = next(p for p in profiles if p["name"] == "Go Profile")
    assert len(go_profile["steps"]) == 1
    assert go_profile["steps"][0]["name"] == "Build"
    assert go_profile["steps"][0]["command"] == "go build ./..."


def test_add_step_to_nonexistent_profile_returns_404(client):
    """Adding a step to a missing profile returns 404."""
    response = client.post("/api/verification/profiles/999999/steps", json={
        "name": "Build",
        "command": "go build ./...",
    })
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_add_step_missing_name_returns_400(client):
    """Adding a step without name returns 400."""
    create_response = client.post("/api/verification/profiles", json={
        "name": "Temp Profile",
        "language": "rust",
    })
    profile_id = create_response.get_json()["id"]
    response = client.post(f"/api/verification/profiles/{profile_id}/steps", json={
        "command": "cargo build",
    })
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_update_step(client):
    """PUT updates step fields."""
    profile_response = client.post("/api/verification/profiles", json={
        "name": "Update Test Profile",
        "language": "python",
    })
    profile_id = profile_response.get_json()["id"]

    step_response = client.post(f"/api/verification/profiles/{profile_id}/steps", json={
        "name": "Lint",
        "command": "ruff check .",
        "enabled": True,
        "timeout": 30,
    })
    step_id = step_response.get_json()["id"]

    update_response = client.put(f"/api/verification/steps/{step_id}", json={
        "command": "ruff check --fix .",
        "timeout": 90,
        "enabled": False,
    })
    assert update_response.status_code == 200
    assert update_response.get_json()["ok"] is True

    profiles = client.get("/api/verification/profiles").get_json()["profiles"]
    profile = next(p for p in profiles if p["name"] == "Update Test Profile")
    step = next(s for s in profile["steps"] if s["id"] == step_id)
    assert step["command"] == "ruff check --fix ."
    assert step["timeout"] == 90
    assert step["enabled"] == 0


def test_update_step_not_found_returns_404(client):
    """PUT on a missing step returns 404."""
    response = client.put("/api/verification/steps/999999", json={"timeout": 60})
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_delete_step(client):
    """DELETE removes a step from its profile."""
    profile_response = client.post("/api/verification/profiles", json={
        "name": "Delete Test Profile",
        "language": "ruby",
    })
    profile_id = profile_response.get_json()["id"]

    step_response = client.post(f"/api/verification/profiles/{profile_id}/steps", json={
        "name": "Test",
        "command": "rspec",
    })
    step_id = step_response.get_json()["id"]

    delete_response = client.delete(f"/api/verification/steps/{step_id}")
    assert delete_response.status_code == 200
    assert delete_response.get_json()["ok"] is True

    profiles = client.get("/api/verification/profiles").get_json()["profiles"]
    profile = next(p for p in profiles if p["name"] == "Delete Test Profile")
    assert all(s["id"] != step_id for s in profile["steps"])


def test_delete_step_not_found_returns_404(client):
    """DELETE on a missing step returns 404."""
    response = client.delete("/api/verification/steps/999999")
    assert response.status_code == 404
    assert "error" in response.get_json()


# ---------------------------------------------------------------------------
# Workspace-scoped endpoints
# ---------------------------------------------------------------------------

def _ws_url(workspace, suffix=""):
    project_id = workspace["project_id"]
    branch = workspace["branch"]
    return f"/api/ws/{project_id}/{branch}/verification{suffix}"


def test_workspace_profiles_empty(client, workspace):
    """No profiles are assigned to a workspace initially."""
    response = client.get(_ws_url(workspace, "/profiles"))
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"profiles": []}


def test_assign_profile_to_workspace(client, workspace):
    """Assign a global profile to a workspace; it appears in workspace profiles."""
    all_profiles = client.get("/api/verification/profiles").get_json()["profiles"]
    python_profile = next(p for p in all_profiles if p["name"] == "Python")
    profile_id = python_profile["id"]

    assign_response = client.post(_ws_url(workspace, "/assign"), json={"profile_id": profile_id})
    assert assign_response.status_code == 200
    data = assign_response.get_json()
    assert data["ok"] is True
    assert "id" in data

    profiles_response = client.get(_ws_url(workspace, "/profiles"))
    profiles = profiles_response.get_json()["profiles"]
    assert len(profiles) == 1
    assert profiles[0]["id"] == profile_id
    assert "assignment_id" in profiles[0]


def test_assign_profile_missing_profile_id_returns_400(client, workspace):
    """POST /assign without profile_id returns 400."""
    response = client.post(_ws_url(workspace, "/assign"), json={})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_assign_nonexistent_profile_returns_404(client, workspace):
    """Assigning a profile that doesn't exist returns 404."""
    response = client.post(_ws_url(workspace, "/assign"), json={"profile_id": 999999})
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_assign_profile_duplicate_returns_409(client, workspace):
    """Assigning the same profile twice to the same workspace returns 409."""
    all_profiles = client.get("/api/verification/profiles").get_json()["profiles"]
    profile_id = all_profiles[0]["id"]

    client.post(_ws_url(workspace, "/assign"), json={"profile_id": profile_id})
    response = client.post(_ws_url(workspace, "/assign"), json={"profile_id": profile_id})
    assert response.status_code == 409
    assert "error" in response.get_json()


def test_unassign_profile(client, workspace):
    """Unassign a profile removes it from workspace profiles."""
    all_profiles = client.get("/api/verification/profiles").get_json()["profiles"]
    profile_id = all_profiles[0]["id"]

    assign_data = client.post(_ws_url(workspace, "/assign"), json={"profile_id": profile_id}).get_json()
    assignment_id = assign_data["id"]

    unassign_response = client.delete(_ws_url(workspace, f"/unassign/{assignment_id}"))
    assert unassign_response.status_code == 200
    assert unassign_response.get_json()["ok"] is True

    profiles = client.get(_ws_url(workspace, "/profiles")).get_json()["profiles"]
    assert profiles == []


def test_unassign_nonexistent_assignment_returns_404(client, workspace):
    """Unassigning a missing assignment returns 404."""
    response = client.delete(_ws_url(workspace, "/unassign/999999"))
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_run_verification_no_profiles(client, workspace):
    """Run returns a no-profiles message when no profiles are assigned."""
    response = client.post(_ws_url(workspace, "/run"), json={})
    assert response.status_code == 200
    data = response.get_json()
    assert "message" in data
    assert data["message"] == "No verification profiles assigned"


def test_run_verification_with_passing_step(client, workspace):
    """Run executes steps and returns a run result with status and step results."""
    profile_response = client.post("/api/verification/profiles", json={
        "name": "Echo Profile",
        "language": "shell",
    })
    profile_id = profile_response.get_json()["id"]

    client.post(f"/api/verification/profiles/{profile_id}/steps", json={
        "name": "Echo",
        "command": "echo hello",
        "enabled": True,
        "timeout": 10,
        "fail_severity": "blocking",
    })

    client.post(_ws_url(workspace, "/assign"), json={"profile_id": profile_id})

    run_response = client.post(_ws_url(workspace, "/run"), json={})
    assert run_response.status_code == 200
    result = run_response.get_json()

    assert result["status"] == "passed"
    assert isinstance(result["steps"], list)
    assert len(result["steps"]) == 1
    assert result["steps"][0]["step_name"] == "Echo"
    assert result["steps"][0]["status"] == "passed"


def test_run_verification_with_failing_step(client, workspace):
    """Run with a failing blocking step records status as failed."""
    profile_response = client.post("/api/verification/profiles", json={
        "name": "Fail Profile",
        "language": "shell",
    })
    profile_id = profile_response.get_json()["id"]

    client.post(f"/api/verification/profiles/{profile_id}/steps", json={
        "name": "Will Fail",
        "command": "exit 1",
        "enabled": True,
        "timeout": 10,
        "fail_severity": "blocking",
    })

    client.post(_ws_url(workspace, "/assign"), json={"profile_id": profile_id})

    run_response = client.post(_ws_url(workspace, "/run"), json={})
    assert run_response.status_code == 200
    result = run_response.get_json()

    assert result["status"] == "failed"
    assert result["steps"][0]["status"] == "failed"


def test_profile_assigned_in_one_workspace_visible_from_another(client, workspace, second_workspace):
    """Assigning a profile via one workspace branch makes it visible from any other branch in the same project."""
    all_profiles = client.get("/api/verification/profiles").get_json()["profiles"]
    python_profile = next(p for p in all_profiles if p["name"] == "Python")
    profile_id = python_profile["id"]

    assign_response = client.post(_ws_url(workspace, "/assign"), json={"profile_id": profile_id})
    assert assign_response.status_code == 200

    profiles_from_second = client.get(_ws_url(second_workspace, "/profiles")).get_json()["profiles"]
    assert len(profiles_from_second) == 1
    assert profiles_from_second[0]["id"] == profile_id


def test_unassign_in_one_workspace_removes_from_all(client, workspace, second_workspace):
    """Unassigning a profile via one workspace branch removes it for the entire project."""
    all_profiles = client.get("/api/verification/profiles").get_json()["profiles"]
    profile_id = all_profiles[0]["id"]

    assign_data = client.post(_ws_url(workspace, "/assign"), json={"profile_id": profile_id}).get_json()
    assignment_id = assign_data["id"]

    client.delete(_ws_url(second_workspace, f"/unassign/{assignment_id}"))

    profiles_from_first = client.get(_ws_url(workspace, "/profiles")).get_json()["profiles"]
    assert profiles_from_first == []


def test_duplicate_assignment_blocked_across_workspaces(client, workspace, second_workspace):
    """Assigning the same profile via a different workspace branch in the same project returns 409."""
    all_profiles = client.get("/api/verification/profiles").get_json()["profiles"]
    profile_id = all_profiles[0]["id"]

    client.post(_ws_url(workspace, "/assign"), json={"profile_id": profile_id})
    response = client.post(_ws_url(second_workspace, "/assign"), json={"profile_id": profile_id})
    assert response.status_code == 409
    assert "error" in response.get_json()
