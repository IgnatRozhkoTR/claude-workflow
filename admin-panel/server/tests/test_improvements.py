"""Tests for improvements API endpoints."""
import pytest


def _insert_improvement(scope, title, description="desc", context=None, status="open"):
    """Insert an improvement directly via report_improvement."""
    from core.db import get_db
    from services import improvement_service
    db = get_db()
    result = improvement_service.report_improvement(db, scope, title, description, context)
    if status == "resolved":
        improvement_service.resolve_improvement(db, result["id"])
    db.commit()
    db.close()
    return result["id"]


def test_list_improvements_empty(client):
    response = client.get("/api/improvements")
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"improvements": []}


def test_list_improvements_with_data(client):
    _insert_improvement("planning", "Improve scope detection", "More context needed")
    _insert_improvement("review", "Add lint step", "Automate lint checks")

    response = client.get("/api/improvements")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["improvements"]) == 2
    titles = [i["title"] for i in data["improvements"]]
    assert "Improve scope detection" in titles
    assert "Add lint step" in titles


def test_list_improvements_filter_scope(client):
    _insert_improvement("planning", "Planning improvement")
    _insert_improvement("review", "Review improvement")

    response = client.get("/api/improvements?scope=planning")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["improvements"]) == 1
    assert data["improvements"][0]["scope"] == "planning"
    assert data["improvements"][0]["title"] == "Planning improvement"


def test_list_improvements_filter_status(client):
    _insert_improvement("planning", "Open one", status="open")
    _insert_improvement("planning", "Resolved one", status="resolved")

    response = client.get("/api/improvements?status=open")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["improvements"]) == 1
    assert data["improvements"][0]["status"] == "open"
    assert data["improvements"][0]["title"] == "Open one"


def test_resolve_improvement(client):
    improvement_id = _insert_improvement("planning", "Fix planning flow")

    response = client.put(f"/api/improvements/{improvement_id}/resolve", json={})
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"ok": True}

    list_response = client.get(f"/api/improvements?status=resolved")
    list_data = list_response.get_json()
    assert len(list_data["improvements"]) == 1
    assert list_data["improvements"][0]["status"] == "resolved"


def test_resolve_improvement_with_note(client):
    improvement_id = _insert_improvement("review", "Add coverage check")

    response = client.put(
        f"/api/improvements/{improvement_id}/resolve",
        json={"note": "Implemented in phase 3 gate"}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"ok": True}

    from core.db import get_db
    db = get_db()
    row = db.execute(
        "SELECT resolved_note, status FROM improvements WHERE id = ?", (improvement_id,)
    ).fetchone()
    db.close()
    assert row["status"] == "resolved"
    assert row["resolved_note"] == "Implemented in phase 3 gate"


def test_reopen_improvement(client):
    improvement_id = _insert_improvement("planning", "Reconsider plan format", status="resolved")

    response = client.put(f"/api/improvements/{improvement_id}/reopen")
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"ok": True}

    from core.db import get_db
    db = get_db()
    row = db.execute(
        "SELECT status, resolved_note, resolved_at FROM improvements WHERE id = ?", (improvement_id,)
    ).fetchone()
    db.close()
    assert row["status"] == "open"
    assert row["resolved_note"] is None
    assert row["resolved_at"] is None


def test_resolve_nonexistent(client):
    response = client.put("/api/improvements/99999/resolve", json={})
    assert response.status_code == 404
    data = response.get_json()
    assert "error" in data
