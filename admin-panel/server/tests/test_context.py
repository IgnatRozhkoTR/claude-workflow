"""Tests for context, discussions, search-paths, and criteria routes."""
import json
from pathlib import Path

from testing_utils import add_criterion

BASE = "/api/ws/test-project/feature/test"


# ── Context CRUD ──────────────────────────────────────────────────────────────

def test_get_context(client, workspace):
    r = client.get(f"{BASE}/context")
    assert r.status_code == 200
    assert "ticket_id" in r.json
    assert "ticket_name" in r.json
    assert "context" in r.json
    assert "refs" in r.json
    assert "discussions" in r.json


def test_get_context_not_found(client, project):
    r = client.get("/api/ws/test-project/nonexistent/context")
    assert r.status_code == 404


def test_update_context_ticket(client, workspace):
    r = client.put(f"{BASE}/context", json={"ticket_id": "PROJ-123", "ticket_name": "My Task"})
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(f"{BASE}/context")
    assert r.json["ticket_id"] == "PROJ-123"
    assert r.json["ticket_name"] == "My Task"


def test_update_context_text(client, workspace):
    r = client.put(f"{BASE}/context", json={"context": "Some context text"})
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(f"{BASE}/context")
    assert r.json["context"] == "Some context text"


def test_update_context_refs(client, workspace):
    r = client.put(f"{BASE}/context", json={"refs": ["src/main.py", "src/"]})
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(f"{BASE}/context")
    assert r.json["refs"] == ["src/main.py", "src/"]


def test_update_context_invalid_refs(client, workspace):
    r = client.put(f"{BASE}/context", json={"refs": "not-a-list"})
    assert r.status_code == 400


# ── Discussions ───────────────────────────────────────────────────────────────

def test_add_discussion(client, workspace):
    r = client.post(f"{BASE}/context/discussions", json={"topic": "Architecture choice"})
    assert r.status_code == 200
    assert r.json["id"]


def test_add_discussion_missing_topic(client, workspace):
    r = client.post(f"{BASE}/context/discussions", json={})
    assert r.status_code == 400


def test_update_discussion_status(client, workspace):
    r = client.post(f"{BASE}/context/discussions", json={"topic": "Deploy strategy"})
    discussion_id = r.json["id"]

    r = client.put(f"{BASE}/context/discussions/{discussion_id}", json={"status": "resolved"})
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(f"{BASE}/context")
    discussion = next(d for d in r.json["discussions"] if d["id"] == discussion_id)
    assert discussion["status"] == "resolved"
    assert discussion["resolved_at"] is not None


def test_reply_to_discussion(client, workspace):
    r = client.post(f"{BASE}/context/discussions", json={"topic": "DB choice"})
    discussion_id = r.json["id"]

    r = client.post(f"{BASE}/context/discussions/{discussion_id}/reply", json={"text": "Use Postgres"})
    assert r.status_code == 200
    assert r.json["id"]

    r = client.get(f"{BASE}/context")
    discussion = next(d for d in r.json["discussions"] if d["id"] == discussion_id)
    assert len(discussion["replies"]) == 1
    assert discussion["replies"][0]["text"] == "Use Postgres"


def test_delete_discussion(client, workspace):
    r = client.post(f"{BASE}/context/discussions", json={"topic": "Temp topic"})
    discussion_id = r.json["id"]

    r = client.delete(f"{BASE}/context/discussions/{discussion_id}")
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(f"{BASE}/context")
    ids = [d["id"] for d in r.json["discussions"]]
    assert discussion_id not in ids


def test_delete_discussion_not_found(client, workspace):
    r = client.delete(f"{BASE}/context/discussions/99999")
    assert r.status_code == 404


# ── Search paths ──────────────────────────────────────────────────────────────

def test_search_paths(client, workspace):
    from testing_utils import _git
    repo = Path(workspace["working_dir"])
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "main.py").write_text("x = 1")
    (repo / "src" / "utils.py").write_text("y = 2")
    _git(str(repo), "add", ".")
    _git(str(repo), "commit", "-m", "Add files")

    r = client.get(f"{BASE}/search-paths", query_string={"q": "src"})
    assert r.status_code == 200
    results = r.json["results"]
    assert len(results) > 0
    assert any("src" in result for result in results)


def test_search_paths_short_query(client, workspace):
    r = client.get(f"{BASE}/search-paths", query_string={"q": "a"})
    assert r.status_code == 200
    assert r.json["results"] == []


# ── Criteria ──────────────────────────────────────────────────────────────────

def test_get_criteria_empty(client, workspace):
    r = client.get(f"{BASE}/criteria")
    assert r.status_code == 200
    assert r.json["criteria"] == []


def test_create_criterion(client, workspace):
    r = client.post(f"{BASE}/criteria", json={"type": "unit_test", "description": "Test user service"})
    assert r.status_code == 201
    assert r.json["ok"]
    assert r.json["id"]


def test_create_criterion_invalid_type(client, workspace):
    r = client.post(f"{BASE}/criteria", json={"type": "invalid", "description": "Something"})
    assert r.status_code == 400


def test_update_criterion_status(client, workspace):
    criterion_id = add_criterion(workspace["id"], cr_type="unit_test", description="Test service")

    r = client.put(f"{BASE}/criteria/{criterion_id}", json={"status": "accepted"})
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(f"{BASE}/criteria")
    criterion = next(c for c in r.json["criteria"] if c["id"] == criterion_id)
    assert criterion["status"] == "accepted"


def test_delete_criterion(client, workspace):
    criterion_id = add_criterion(workspace["id"], cr_type="unit_test", description="To be deleted")

    r = client.delete(f"{BASE}/criteria/{criterion_id}")
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(f"{BASE}/criteria")
    ids = [c["id"] for c in r.json["criteria"]]
    assert criterion_id not in ids


def test_validate_custom_criterion(client, workspace):
    from testing_utils import add_criterion
    criterion_id = add_criterion(workspace["id"], cr_type="custom", description="Manual check")

    # Accept it first (required before validation)
    client.put(f"{BASE}/criteria/{criterion_id}", json={"status": "accepted"})

    # Validate it
    r = client.put(f"{BASE}/criteria/{criterion_id}/validate", json={"passed": True})
    assert r.status_code == 200
    assert r.json["ok"]

    # Verify it's validated
    r = client.get(f"{BASE}/criteria")
    criterion = next(c for c in r.json["criteria"] if c["id"] == criterion_id)
    assert criterion["validated"] == 1


def test_validate_non_custom_criterion_rejected(client, workspace):
    from testing_utils import add_criterion
    criterion_id = add_criterion(workspace["id"], cr_type="unit_test", description="Test service")
    r = client.put(f"{BASE}/criteria/{criterion_id}/validate", json={"passed": True})
    assert r.status_code == 400
    assert "custom" in r.json["error"].lower()


def test_validate_criterion_missing_passed(client, workspace):
    from testing_utils import add_criterion
    criterion_id = add_criterion(workspace["id"], cr_type="custom", description="Manual check")
    r = client.put(f"{BASE}/criteria/{criterion_id}/validate", json={})
    assert r.status_code == 400


def test_reject_custom_criterion(client, workspace):
    from testing_utils import add_criterion
    criterion_id = add_criterion(workspace["id"], cr_type="custom", description="Manual check")
    client.put(f"{BASE}/criteria/{criterion_id}", json={"status": "accepted"})
    r = client.put(f"{BASE}/criteria/{criterion_id}/validate", json={"passed": False, "message": "Not satisfied"})
    assert r.status_code == 200

    r = client.get(f"{BASE}/criteria")
    criterion = next(c for c in r.json["criteria"] if c["id"] == criterion_id)
    assert criterion["validated"] == -1
    assert criterion["validation_message"] == "Not satisfied"


# ── Criteria API route gaps ──────────────────────────────────────────────────


def test_get_criteria_filter_by_status(client, workspace):
    """GET criteria with ?status=accepted returns only accepted criteria."""
    client.post(f"{BASE}/criteria", json={"type": "unit_test", "description": "First"})
    r2 = client.post(f"{BASE}/criteria", json={"type": "unit_test", "description": "Second"})
    second_id = r2.json["id"]

    client.put(f"{BASE}/criteria/{second_id}", json={"status": "accepted"})

    r = client.get(f"{BASE}/criteria", query_string={"status": "accepted"})
    assert r.status_code == 200
    assert len(r.json["criteria"]) == 1
    assert r.json["criteria"][0]["id"] == second_id
    assert r.json["criteria"][0]["status"] == "accepted"


def test_get_criteria_filter_by_type(client, workspace):
    """GET criteria with ?type=custom returns only custom criteria."""
    client.post(f"{BASE}/criteria", json={"type": "unit_test", "description": "A unit test"})
    client.post(f"{BASE}/criteria", json={"type": "custom", "description": "A custom check"})

    r = client.get(f"{BASE}/criteria", query_string={"type": "custom"})
    assert r.status_code == 200
    assert len(r.json["criteria"]) == 1
    assert r.json["criteria"][0]["type"] == "custom"
    assert r.json["criteria"][0]["description"] == "A custom check"


def test_post_criteria_missing_type(client, workspace):
    """POST criteria without type returns 400."""
    r = client.post(f"{BASE}/criteria", json={"description": "foo"})
    assert r.status_code == 400


def test_post_criteria_missing_description(client, workspace):
    """POST criteria without description returns 400."""
    r = client.post(f"{BASE}/criteria", json={"type": "unit_test"})
    assert r.status_code == 400


def test_put_criteria_reject(client, workspace):
    """PUT criteria with status=rejected changes the criterion status."""
    criterion_id = add_criterion(workspace["id"], cr_type="unit_test", description="To reject")

    r = client.put(f"{BASE}/criteria/{criterion_id}", json={"status": "rejected"})
    assert r.status_code == 200
    assert r.json["ok"]

    r = client.get(f"{BASE}/criteria")
    criterion = next(c for c in r.json["criteria"] if c["id"] == criterion_id)
    assert criterion["status"] == "rejected"


def test_put_criteria_not_found(client, workspace):
    """PUT criteria for non-existent ID returns 404."""
    r = client.put(f"{BASE}/criteria/999", json={"status": "accepted"})
    assert r.status_code == 404


def test_delete_criteria_not_found(client, workspace):
    """DELETE criteria for non-existent ID returns 404."""
    r = client.delete(f"{BASE}/criteria/999")
    assert r.status_code == 404
