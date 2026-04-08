"""Tests for core.paths — repo-relative path resolution."""
import importlib
import sys
from pathlib import Path

import pytest


def test_repo_root_contains_admin_panel():
    from core.paths import REPO_ROOT
    assert (REPO_ROOT / "admin-panel").is_dir(), (
        f"REPO_ROOT={REPO_ROOT} does not contain admin-panel/"
    )


def test_default_hooks_dir_exists():
    from core.paths import DEFAULT_HOOKS_DIR, REPO_ROOT
    assert DEFAULT_HOOKS_DIR == REPO_ROOT / "claude" / "hooks", (
        f"DEFAULT_HOOKS_DIR={DEFAULT_HOOKS_DIR} is not at REPO_ROOT/claude/hooks"
    )
    assert DEFAULT_HOOKS_DIR.is_dir(), (
        f"DEFAULT_HOOKS_DIR={DEFAULT_HOOKS_DIR} does not exist"
    )


def test_payload_layout_directories_exist():
    from core.paths import REPO_ROOT
    assert (REPO_ROOT / "claude").is_dir(), f"REPO_ROOT/claude does not exist"
    assert (REPO_ROOT / "codex").is_dir(), f"REPO_ROOT/codex does not exist"


def test_hook_command_contains_no_home_claude():
    from core.paths import hook_command, REPO_ROOT
    cmd = hook_command("session-start.py")
    # Must not contain the unexpanded tilde form.
    assert "~/.claude" not in cmd
    # The path must be absolute (no tilde, no relative segments).
    assert cmd.startswith("python3 /")
    # The resolved path must be rooted inside REPO_ROOT, not somewhere else.
    hook_path = cmd[len("python3 "):]
    assert hook_path.startswith(str(REPO_ROOT)), (
        f"hook_command path {hook_path!r} is not under REPO_ROOT {REPO_ROOT}"
    )


def test_hook_command_references_hooks_dir():
    from core.paths import hook_command, DEFAULT_HOOKS_DIR
    cmd = hook_command("session-start.py")
    assert cmd.startswith("python3 ")
    assert str(DEFAULT_HOOKS_DIR / "session-start.py") in cmd


def test_hook_command_bash_interpreter():
    from core.paths import hook_command, DEFAULT_HOOKS_DIR
    cmd = hook_command("user-prompt-submit.sh", interpreter="bash")
    assert cmd.startswith("bash ")
    assert str(DEFAULT_HOOKS_DIR / "user-prompt-submit.sh") in cmd


def test_governed_workflow_repo_env_override(monkeypatch, tmp_path):
    """GOVERNED_WORKFLOW_REPO env var overrides the parents[] computation."""
    fake_root = tmp_path / "fake-repo"
    fake_root.mkdir()

    monkeypatch.setenv("GOVERNED_WORKFLOW_REPO", str(fake_root))

    # Force reload of the module so the env var is re-evaluated at import time.
    if "core.paths" in sys.modules:
        del sys.modules["core.paths"]

    import core.paths as paths_mod
    try:
        assert paths_mod.REPO_ROOT == fake_root.resolve()
    finally:
        # Restore original module so subsequent tests are unaffected.
        del sys.modules["core.paths"]
        monkeypatch.delenv("GOVERNED_WORKFLOW_REPO", raising=False)
        import core.paths  # noqa: F401 — re-import original


def test_telegram_state_dir_env_override(monkeypatch, tmp_path):
    """GOVERNED_WORKFLOW_TELEGRAM_STATE env var overrides TELEGRAM_STATE_DIR."""
    fake_tg = tmp_path / "tg-state"
    fake_tg.mkdir()

    monkeypatch.setenv("GOVERNED_WORKFLOW_TELEGRAM_STATE", str(fake_tg))

    if "core.paths" in sys.modules:
        del sys.modules["core.paths"]

    import core.paths as paths_mod
    try:
        assert paths_mod.TELEGRAM_STATE_DIR == fake_tg
    finally:
        del sys.modules["core.paths"]
        monkeypatch.delenv("GOVERNED_WORKFLOW_TELEGRAM_STATE", raising=False)
        import core.paths  # noqa: F401 — re-import original
