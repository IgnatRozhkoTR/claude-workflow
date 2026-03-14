"""Tests for plan versioning: restore-plan endpoint and has_prev_plan state field."""
import json

from testing_utils import set_phase

PLAN_A = json.dumps({"description": "Plan A", "systemDiagram": "", "execution": []})
PLAN_B = json.dumps({"description": "Plan B", "systemDiagram": "", "execution": []})
SCOPE_A = json.dumps({"must": ["src/"], "may": []})
SCOPE_B = json.dumps({"must": ["lib/"], "may": []})


def _restore_url(workspace):
    return f"/api/ws/{workspace['project_id']}/{workspace['branch']}/restore-plan"


def _state_url(workspace):
    return f"/api/ws/{workspace['project_id']}/{workspace['branch']}/state"


# ── restore-plan ─────────────────────────────────────────────────────────────

def test_restore_plan_swaps_plans(client, workspace):
    set_phase(workspace["id"], "1.0",
              plan_json=PLAN_A, plan_status="pending",
              prev_plan_json=PLAN_B, prev_plan_status="approved",
              prev_phase="1.0", prev_scope_status="pending")

    resp = client.post(_restore_url(workspace))
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    state = client.get(_state_url(workspace)).get_json()
    assert state["plan"]["description"] == "Plan B"
    assert state["plan_status"] == "approved"
    assert state["prev_plan_status"] == "pending"

    # Restore again — Plan A should come back
    resp2 = client.post(_restore_url(workspace))
    assert resp2.status_code == 200

    state2 = client.get(_state_url(workspace)).get_json()
    assert state2["plan"]["description"] == "Plan A"
    assert state2["plan_status"] == "pending"


def test_restore_plan_no_previous_returns_404(client, workspace):
    set_phase(workspace["id"], "1.0", plan_json=PLAN_A)

    resp = client.post(_restore_url(workspace))
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_restore_plan_restores_phase(client, workspace):
    set_phase(workspace["id"], "3.2.0",
              plan_json=PLAN_A, plan_status="pending",
              prev_plan_json=PLAN_B, prev_phase="2.0",
              prev_plan_status="pending", prev_scope_status="pending")

    resp = client.post(_restore_url(workspace))
    assert resp.status_code == 200

    data = resp.get_json()
    assert data["phase"] == "2.0"

    state = client.get(_state_url(workspace)).get_json()
    assert state["phase"] == "2.0"


def test_restore_plan_records_phase_history(client, workspace):
    set_phase(workspace["id"], "3.2.0",
              plan_json=PLAN_A, plan_status="pending",
              prev_plan_json=PLAN_B, prev_phase="2.0",
              prev_plan_status="pending", prev_scope_status="pending")

    client.post(_restore_url(workspace))

    state = client.get(_state_url(workspace)).get_json()
    history = state["phaseHistory"]
    phase_changes = [h for h in history if h["from"] == "3.2.0" and h["to"] == "2.0"]
    assert len(phase_changes) == 1


def test_restore_plan_restores_scope_and_status(client, workspace):
    set_phase(workspace["id"], "1.0",
              plan_json=PLAN_A, plan_status="pending",
              scope_json=SCOPE_A, scope_status="pending",
              prev_plan_json=PLAN_B, prev_plan_status="approved",
              prev_scope_json=SCOPE_B, prev_scope_status="approved", prev_phase="1.0")

    resp = client.post(_restore_url(workspace))
    assert resp.status_code == 200

    state = client.get(_state_url(workspace)).get_json()
    assert state["scope"] == {"must": ["lib/"], "may": []}
    assert state["scope_status"] == "approved"
    assert state["plan_status"] == "approved"
    assert state["prev_plan_status"] == "pending"


def test_restore_plan_user_can_restore_approved_plan(client, workspace):
    set_phase(workspace["id"], "1.0",
              plan_json=PLAN_A, plan_status="approved",
              prev_plan_json=PLAN_B, prev_plan_status="pending",
              prev_phase="1.0", prev_scope_status="pending")

    resp = client.post(_restore_url(workspace))
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    state = client.get(_state_url(workspace)).get_json()
    assert state["plan"]["description"] == "Plan B"


# ── state: has_prev_plan ─────────────────────────────────────────────────────

def test_state_has_prev_plan_false_when_no_previous(client, workspace):
    state = client.get(_state_url(workspace)).get_json()
    assert state["has_prev_plan"] is False


def test_state_has_prev_plan_true_when_previous_exists(client, workspace):
    set_phase(workspace["id"], "1.0",
              plan_json=PLAN_A, plan_status="pending",
              prev_plan_json=PLAN_B, prev_plan_status="approved")

    state = client.get(_state_url(workspace)).get_json()
    assert state["has_prev_plan"] is True
    assert state["prev_plan_status"] == "approved"
