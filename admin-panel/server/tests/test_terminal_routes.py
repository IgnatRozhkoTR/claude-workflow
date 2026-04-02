"""Tests for terminal launch routes."""
import routes.terminal_routes as terminal_routes

from core.global_flags import CODEX_PHASE1_FLAG, set_flag_enabled
from testing_utils import set_phase


def _enable_codex_phase1():
    from core.db import get_db

    db = get_db()
    set_flag_enabled(db, CODEX_PHASE1_FLAG, True)
    db.commit()
    db.close()


def test_workspace_state_includes_global_codex_phase1_flag(client, workspace):
    _enable_codex_phase1()
    response = client.get(f"/api/ws/{workspace['project_id']}/feature/test/state")
    assert response.status_code == 200
    assert response.get_json()["codex_phase1_globally_enabled"] is True


def test_start_codex_phase1_requires_global_flag(client, workspace, monkeypatch):
    monkeypatch.setattr(terminal_routes, "tmux_available", lambda: True)

    response = client.post(f"/api/ws/{workspace['project_id']}/feature/test/terminal/codex-phase1/start", json={})
    assert response.status_code == 409
    assert "disabled" in response.get_json()["error"].lower()


def test_start_codex_phase1_rejects_after_preparation(client, workspace, monkeypatch):
    _enable_codex_phase1()
    set_phase(workspace["id"], "2.0")
    monkeypatch.setattr(terminal_routes, "tmux_available", lambda: True)

    response = client.post(f"/api/ws/{workspace['project_id']}/feature/test/terminal/codex-phase1/start", json={})
    assert response.status_code == 409
    assert "preparation" in response.get_json()["error"].lower()


def test_start_codex_phase1_uses_dedicated_session(client, workspace, monkeypatch):
    _enable_codex_phase1()

    created = {}
    sent = {}

    monkeypatch.setattr(terminal_routes, "tmux_available", lambda: True)
    monkeypatch.setattr(terminal_routes, "session_exists", lambda name: False)
    monkeypatch.setattr(
        terminal_routes,
        "create_session",
        lambda name, working_dir, env=None: created.update({"name": name, "working_dir": working_dir, "env": env}),
    )
    monkeypatch.setattr(
        terminal_routes,
        "send_keys",
        lambda name, command: sent.update({"name": name, "command": command}),
    )

    response = client.post(f"/api/ws/{workspace['project_id']}/feature/test/terminal/codex-phase1/start", json={})
    assert response.status_code == 200

    data = response.get_json()
    assert data["kind"] == "codex-phase1"
    assert created["name"] == data["session"]
    assert created["name"].endswith("codex-phase1")
    assert created["working_dir"] == workspace["working_dir"]
    assert sent["name"] == created["name"]
    assert "run_codex_phase1.py" in sent["command"]
