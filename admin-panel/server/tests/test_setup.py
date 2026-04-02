"""Tests for setup-scoped device feature flags."""


def test_get_setup_features_default_off(client):
    response = client.get("/api/setup/features")
    assert response.status_code == 200
    assert response.get_json()["codex_enabled"] is False


def test_update_setup_features(client):
    response = client.put("/api/setup/features", json={"codex_enabled": True})
    assert response.status_code == 200
    assert response.get_json()["codex_enabled"] is True

    response = client.get("/api/setup/features")
    assert response.status_code == 200
    assert response.get_json()["codex_enabled"] is True
