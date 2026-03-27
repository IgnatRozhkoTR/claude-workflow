"""Tests for modules discovery and enabled-state endpoints."""


def test_list_modules(client):
    """GET /api/modules returns list (may be empty or contain telegram)."""
    response = client.get("/api/modules")
    assert response.status_code == 200
    data = response.get_json()
    assert "modules" in data
    assert isinstance(data["modules"], list)


def test_list_modules_structure(client):
    """Each module has id, name, description, path, has_skill fields."""
    response = client.get("/api/modules")
    assert response.status_code == 200
    data = response.get_json()
    for module in data["modules"]:
        assert "id" in module
        assert "name" in module
        assert "description" in module
        assert "path" in module
        assert "has_skill" in module
        assert module["has_skill"] is True


def test_list_modules_contains_telegram(client):
    """GET /api/modules includes telegram module from ~/.claude/modules/."""
    response = client.get("/api/modules")
    assert response.status_code == 200
    data = response.get_json()
    ids = [m["id"] for m in data["modules"]]
    assert "telegram" in ids


def test_get_enabled_modules_empty(client):
    """GET /api/modules/enabled returns empty list initially."""
    response = client.get("/api/modules/enabled")
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"modules": []}


def test_set_enabled_modules(client):
    """POST /api/modules/enabled saves module IDs."""
    response = client.post("/api/modules/enabled", json={"modules": ["telegram"]})
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"status": "saved"}


def test_set_enabled_modules_replaces(client):
    """POST /api/modules/enabled replaces previous list entirely."""
    client.post("/api/modules/enabled", json={"modules": ["telegram", "other"]})
    client.post("/api/modules/enabled", json={"modules": ["telegram"]})
    response = client.get("/api/modules/enabled")
    assert response.status_code == 200
    data = response.get_json()
    assert data["modules"] == ["telegram"]


def test_set_enabled_modules_empty(client):
    """POST /api/modules/enabled with empty list clears all."""
    client.post("/api/modules/enabled", json={"modules": ["telegram"]})
    client.post("/api/modules/enabled", json={"modules": []})
    response = client.get("/api/modules/enabled")
    assert response.status_code == 200
    data = response.get_json()
    assert data["modules"] == []


def test_get_enabled_after_set(client):
    """GET returns what was previously POSTed."""
    client.post("/api/modules/enabled", json={"modules": ["telegram", "other-module"]})
    response = client.get("/api/modules/enabled")
    assert response.status_code == 200
    data = response.get_json()
    assert sorted(data["modules"]) == sorted(["telegram", "other-module"])
