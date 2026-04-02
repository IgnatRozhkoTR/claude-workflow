"""Tests for workspace state routes."""
import json
from datetime import date

import pytest

import routes.state as state_routes

from core.global_flags import set_codex_enabled
from testing_utils import set_phase, add_progress, add_research


def _ws_url(workspace, path):
    return f"/api/ws/{workspace['project_id']}/feature/test/{path}"


def test_get_workspace_state(client, workspace):
    response = client.get(_ws_url(workspace, "state"))
    assert response.status_code == 200
    data = response.get_json()
    assert data["phase"] == "0"
    assert "scope" in data
    assert "plan" in data
    assert "phaseHistory" in data
    assert "research" in data
    assert "progress" in data


def test_get_workspace_state_not_found(client, project):
    url = f"/api/ws/{project['id']}/feature/nonexistent/state"
    response = client.get(url)
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_set_scope(client, workspace):
    scope = {"must": ["src/"], "may": ["tests/"]}
    response = client.put(_ws_url(workspace, "scope"), json={"scope": scope})
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["scope"] == scope


def test_set_scope_during_execution(client, workspace):
    set_phase(workspace["id"], "3.1.0")
    scope = {"3.1": {"must": ["src/"], "may": ["tests/"]}}
    response = client.put(_ws_url(workspace, "scope"), json={"scope": scope})
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True

    state = client.get(_ws_url(workspace, "state")).get_json()
    assert state["scope"] == scope


def test_set_scope_not_found(client, project):
    url = f"/api/ws/{project['id']}/feature/nonexistent/scope"
    response = client.put(url, json={"scope": {"must": [], "may": []}})
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_set_scope_status(client, workspace):
    response = client.post(_ws_url(workspace, "scope-status"), json={"status": "approved"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["scope_status"] == "approved"


def test_set_scope_status_invalid(client, workspace):
    response = client.post(_ws_url(workspace, "scope-status"), json={"status": "invalid"})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_set_phase(client, workspace):
    response = client.put(_ws_url(workspace, "phase"), json={"phase": "1.0"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["phase"] == "1.0"
    assert data["previous_phase"] == "0"

    state = client.get(_ws_url(workspace, "state")).get_json()
    history = state["phaseHistory"]
    assert len(history) == 1
    assert history[0]["from"] == "0"
    assert history[0]["to"] == "1.0"


def test_set_phase_to_agentic_review_starts_codex_review_when_enabled(client, workspace, monkeypatch):
    from core.db import get_db

    db = get_db()
    set_codex_enabled(db, True)
    db.execute("UPDATE workspaces SET codex_review_enabled = 1 WHERE id = ?", (workspace["id"],))
    db.commit()
    db.close()

    started = {}
    monkeypatch.setattr(
        state_routes,
        "maybe_start_codex_review_for_workspace",
        lambda workspace_id: started.update({"workspace_id": workspace_id}),
    )

    response = client.put(_ws_url(workspace, "phase"), json={"phase": "4.0"})
    assert response.status_code == 200
    assert started["workspace_id"] == workspace["id"]


def test_set_phase_normalizes(client, workspace):
    response = client.put(_ws_url(workspace, "phase"), json={"phase": "1"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["phase"] == "1.0"


def test_set_phase_invalid(client, workspace):
    response = client.put(_ws_url(workspace, "phase"), json={"phase": "99"})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_set_phase_not_found(client, project):
    url = f"/api/ws/{project['id']}/feature/nonexistent/phase"
    response = client.put(url, json={"phase": "1.0"})
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_get_gate_nonce(client, workspace):
    set_phase(workspace["id"], "2.1", gate_nonce="test-nonce-123")
    response = client.get(_ws_url(workspace, "gate-nonce"))
    assert response.status_code == 200
    data = response.get_json()
    assert data["nonce"] == "test-nonce-123"


def test_get_gate_nonce_none(client, workspace):
    response = client.get(_ws_url(workspace, "gate-nonce"))
    assert response.status_code == 200
    data = response.get_json()
    assert data["nonce"] is None


def test_query_progress(client, workspace):
    add_progress(workspace["id"], "1.0", "Assessment done")
    today = date.today().isoformat()
    response = client.get(f"/api/progress?date={today}")
    assert response.status_code == 200
    data = response.get_json()
    entries = data["entries"]
    assert len(entries) == 1
    assert entries[0]["phase"] == "1.0"
    assert entries[0]["summary"] == "Assessment done"


def test_query_progress_missing_date(client):
    response = client.get("/api/progress")
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_toggle_research_proven(client, workspace):
    research_id = add_research(workspace["id"], topic="Auth flow", proven=0)
    url = _ws_url(workspace, f"research/{research_id}/prove")
    response = client.post(url, json={"proven": True})
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["id"] == research_id
    assert data["proven"] == 1


def test_delete_research(client, workspace):
    research_id = add_research(workspace["id"])

    response = client.delete(_ws_url(workspace, f"research/{research_id}"))
    assert response.status_code == 200
    assert response.get_json()["ok"]

    state = client.get(_ws_url(workspace, "state")).get_json()
    assert all(entry["id"] != research_id for entry in state["research"])


def test_delete_research_not_found(client, workspace):
    response = client.delete(_ws_url(workspace, "research/99999"))
    assert response.status_code == 404


def test_set_plan_status(client, workspace):
    r = client.post("/api/ws/test-project/feature/test/plan-status", json={"status": "approved"})
    assert r.status_code == 200
    assert r.json["plan_status"] == "approved"


def test_set_plan_status_invalid(client, workspace):
    r = client.post("/api/ws/test-project/feature/test/plan-status", json={"status": "invalid"})
    assert r.status_code == 400


def test_set_codex_review_requires_global_flag(client, workspace):
    response = client.put(_ws_url(workspace, "codex-review"), json={"enabled": True})
    assert response.status_code == 409


def test_set_codex_review_updates_workspace(client, workspace):
    from core.db import get_db

    db = get_db()
    set_codex_enabled(db, True)
    db.commit()
    db.close()

    response = client.put(_ws_url(workspace, "codex-review"), json={"enabled": True})
    assert response.status_code == 200
    assert response.get_json()["codex_review_enabled"] is True

    state = client.get(_ws_url(workspace, "state")).get_json()
    assert state["codex_review_enabled"] is True


# ── Can-modify endpoint ──────────────────────────────────────────────────────

def test_can_modify_claude_folder_always_allowed(client, workspace):
    """Files in .claude/ are always allowed regardless of scope/plan status."""
    r = client.post("/api/ws/test-project/feature/test/can-modify", json={"file": ".claude/memory/notes.md"})
    assert r.status_code == 200
    assert r.json["allowed"] is True


def test_can_modify_missing_file_param(client, workspace):
    r = client.post("/api/ws/test-project/feature/test/can-modify", json={})
    assert r.status_code == 400


def test_can_modify_scope_not_approved(client, workspace):
    """Scope not approved — modification denied."""
    from testing_utils import set_phase
    set_phase(workspace["id"], "3.1.0", scope_status="pending")
    r = client.post("/api/ws/test-project/feature/test/can-modify", json={"file": "src/main.py"})
    assert r.status_code == 200
    assert r.json["allowed"] is False
    assert "scope" in r.json["reason"].lower()


def test_can_modify_plan_not_approved(client, workspace):
    """Plan exists but not approved — modification denied."""
    from testing_utils import set_phase, make_plan_json
    plan = make_plan_json(1)
    set_phase(workspace["id"], "3.1.0", plan_json=plan, plan_status="pending", scope_status="approved")
    r = client.post("/api/ws/test-project/feature/test/can-modify", json={"file": "src/main.py"})
    assert r.status_code == 200
    assert r.json["allowed"] is False
    assert "plan" in r.json["reason"].lower()


def test_can_modify_file_in_scope(client, workspace):
    """File matches scope pattern — allowed."""
    import json
    from testing_utils import set_phase, make_plan_json
    scope = json.dumps({"must": ["src/"], "may": ["tests/"]})
    plan = make_plan_json(1)
    set_phase(workspace["id"], "3.1.0", scope_json=scope, scope_status="approved", plan_json=plan, plan_status="approved")
    r = client.post("/api/ws/test-project/feature/test/can-modify", json={"file": "src/main.py"})
    assert r.status_code == 200
    assert r.json["allowed"] is True


def test_can_modify_file_outside_scope(client, workspace):
    """File doesn't match any scope pattern — denied."""
    import json
    from testing_utils import set_phase, make_plan_json
    scope = json.dumps({"3.1": {"must": ["src/"], "may": ["tests/"]}})
    plan = make_plan_json(1)
    set_phase(workspace["id"], "3.1.0", scope_json=scope, scope_status="approved", plan_json=plan, plan_status="approved")
    r = client.post("/api/ws/test-project/feature/test/can-modify", json={"file": "docs/readme.md"})
    assert r.status_code == 200
    assert r.json["allowed"] is False
    assert "outside" in r.json["reason"].lower()
