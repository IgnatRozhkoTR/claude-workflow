"""Tests for setup-scoped device feature flags and skill path resolution."""
from pathlib import Path


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


def test_setup_skill_path_does_not_reference_home_claude():
    """The setup instruction prompt must reference the repo-relative skill path, not ~/.claude."""
    import importlib.util
    import types
    import sys
    from pathlib import Path

    from core.paths import DEFAULT_SKILLS_DIR

    # flask_sock is an optional runtime dep not installed in the test environment.
    # Stub it out so we can import routes.setup for the path-resolution test only.
    flask_sock_stub = types.ModuleType("flask_sock")
    flask_sock_stub.Sock = type("Sock", (), {})
    sys.modules.setdefault("flask_sock", flask_sock_stub)

    # Import routes.setup directly (bypassing routes/__init__.py which also
    # triggers flask_sock via terminal_routes — pre-existing missing-dep issue).
    setup_module_path = Path(__file__).resolve().parent.parent / "routes" / "setup.py"
    module_key = "routes_setup_direct_3_3"
    if module_key in sys.modules:
        del sys.modules[module_key]
    spec = importlib.util.spec_from_file_location(module_key, str(setup_module_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = mod
    spec.loader.exec_module(mod)

    expected_skill_path = DEFAULT_SKILLS_DIR / "setup" / "SKILL.md"

    assert "~/.claude" not in str(expected_skill_path), (
        f"DEFAULT_SKILLS_DIR itself still points into ~/.claude: {DEFAULT_SKILLS_DIR}"
    )

    prompt = mod._build_prompt_for_test()
    assert "~/.claude" not in prompt, (
        "setup prompt contains a ~/.claude reference — it must use DEFAULT_SKILLS_DIR"
    )
    assert str(expected_skill_path) in prompt, (
        f"setup prompt does not reference expected skill path {expected_skill_path}"
    )
