import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from testing_utils import _git


def test_list_branches(client, project):
    r = client.get(f"/api/projects/{project['id']}/branches")
    assert r.status_code == 200
    assert "develop" in r.json["local"]


def test_list_branches_not_found(client):
    r = client.get("/api/projects/nonexistent/branches")
    assert r.status_code == 404


def test_list_workspaces_empty(client, project):
    r = client.get(f"/api/projects/{project['id']}/workspaces")
    assert r.status_code == 200
    assert r.json["workspaces"] == []


def test_create_workspace(client, project):
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/new-ws", "source": "develop", "worktree": True},
    )
    assert r.status_code == 201
    assert r.json["branch"] == "feature/new-ws"


def test_create_workspace_no_worktree(client, project):
    _git(project["path"], "checkout", "-b", "other-branch")
    _git(project["path"], "checkout", "develop")
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "other-branch", "source": "develop", "worktree": False},
    )
    assert r.status_code in (201, 409)


def test_create_workspace_missing_branch(client, project):
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"source": "develop"},
    )
    assert r.status_code == 400


def test_create_workspace_missing_source(client, project):
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/test-src", "source": "nonexistent-branch"},
    )
    assert r.status_code == 404


def test_create_workspace_duplicate(client, project):
    client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/dup", "source": "develop", "worktree": True},
    )
    r = client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/dup", "source": "develop", "worktree": True},
    )
    assert r.status_code == 409


def test_list_workspaces_after_create(client, project):
    client.post(
        f"/api/projects/{project['id']}/workspaces",
        json={"branch": "feature/listed", "source": "develop", "worktree": True},
    )
    r = client.get(f"/api/projects/{project['id']}/workspaces")
    assert r.status_code == 200
    assert len(r.json["workspaces"]) >= 1


def test_archive_workspace(client, workspace, project):
    r = client.put(f"/api/ws/{project['id']}/feature/test/archive")
    assert r.status_code == 200
    assert r.json["status"] == "archived"


def test_archive_workspace_not_found(client, project):
    r = client.put(f"/api/ws/{project['id']}/nonexistent/archive")
    assert r.status_code == 404


def test_archive_workspace_already_archived(client, workspace, project):
    client.put(f"/api/ws/{project['id']}/feature/test/archive")
    r = client.put(f"/api/ws/{project['id']}/feature/test/archive")
    # After archiving, sanitized_branch gains a timestamp suffix so the second
    # lookup by the original branch name finds no active workspace.
    assert r.status_code == 404


# ─── 3.2 MERGE LAYER TESTS ────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]  # worktrees/Restructuring
_MD_SEPARATOR = "\n\n---\n\n# Governed Workflow Defaults\n\n"


@pytest.fixture
def project_with_assets(git_repo):
    """Git repo with project-level .claude/, .codex/, CLAUDE.md, AGENTS.md and .mcp.json."""
    repo = Path(git_repo)

    # Project-level .claude/agents and .claude/rules
    (repo / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "agents" / "custom.md").write_text("# Custom Project Agent")
    (repo / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "rules" / "project.md").write_text("# Project Rule")

    # Project-level .codex
    (repo / ".codex" / "agents").mkdir(parents=True, exist_ok=True)
    (repo / ".codex" / "agents" / "custom.md").write_text("# Custom Codex Agent")

    # Project-level CLAUDE.md and AGENTS.md with unique markers
    (repo / "CLAUDE.md").write_text("PROJECT_CLAUDE_MD_MARKER")
    (repo / "AGENTS.md").write_text("PROJECT_AGENTS_MD_MARKER")

    # Project-level .mcp.json with an extra server
    (repo / ".mcp.json").write_text(json.dumps({
        "mcpServers": {
            "custom": {"command": "echo", "args": ["hello"]}
        }
    }, indent=2))

    _git(git_repo, "add", "-A")
    _git(git_repo, "commit", "-m", "Add project assets")
    return git_repo


def _import_workspaces_module():
    """Import routes.workspaces directly, bypassing the routes package __init__."""
    import importlib.util, sys
    server_dir = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "routes.workspaces",
        server_dir / "routes" / "workspaces.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("routes.workspaces", mod)
    spec.loader.exec_module(mod)
    return mod


_WORKSPACES = _import_workspaces_module()


def _call_install_worktree_configs(project_path, wt_path):
    """Call the internal bootstrap function."""
    _WORKSPACES._install_worktree_configs(project_path, wt_path)


class TestMergeLayer:
    """Integration tests for the _merge_project_assets merge logic."""

    def test_project_agent_preserved_in_worktree(self, project_with_assets, tmp_path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _call_install_worktree_configs(project_with_assets, wt)
        assert (wt / ".claude" / "agents" / "custom.md").read_text() == "# Custom Project Agent"

    def test_repo_default_agent_also_present(self, project_with_assets, tmp_path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _call_install_worktree_configs(project_with_assets, wt)
        # At least one file from the repo default agents dir must be present
        repo_agents = list((REPO_ROOT / "claude" / "agents").glob("*.md"))
        assert repo_agents, "Repo must have at least one default agent file"
        assert (wt / ".claude" / "agents" / repo_agents[0].name).exists()

    def test_codex_agent_preserved_in_worktree(self, project_with_assets, tmp_path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _call_install_worktree_configs(project_with_assets, wt)
        assert (wt / ".codex" / "agents" / "custom.md").read_text() == "# Custom Codex Agent"

    def test_claude_md_concatenated_with_separator(self, project_with_assets, tmp_path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _call_install_worktree_configs(project_with_assets, wt)
        content = (wt / "CLAUDE.md").read_text()
        assert "PROJECT_CLAUDE_MD_MARKER" in content
        assert _MD_SEPARATOR in content

    def test_agents_md_concatenated_with_separator(self, project_with_assets, tmp_path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _call_install_worktree_configs(project_with_assets, wt)
        content = (wt / "AGENTS.md").read_text()
        assert "PROJECT_AGENTS_MD_MARKER" in content
        assert _MD_SEPARATOR in content

    def test_claude_md_project_content_appears_first(self, project_with_assets, tmp_path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _call_install_worktree_configs(project_with_assets, wt)
        content = (wt / "CLAUDE.md").read_text()
        project_pos = content.index("PROJECT_CLAUDE_MD_MARKER")
        sep_pos = content.index(_MD_SEPARATOR)
        assert project_pos < sep_pos

    def test_claude_md_is_regular_file_not_symlink(self, project_with_assets, tmp_path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _call_install_worktree_configs(project_with_assets, wt)
        target = wt / "CLAUDE.md"
        assert target.exists()
        assert not target.is_symlink()

    def test_mcp_json_symlinked_to_project(self, project_with_assets, tmp_path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _call_install_worktree_configs(project_with_assets, wt)
        dst_mcp = wt / ".mcp.json"
        assert dst_mcp.is_symlink()
        data = json.loads(dst_mcp.read_text())
        assert "workspace" in data["mcpServers"]
        assert "custom" in data["mcpServers"]

    def test_rules_symlinked_to_project(self, project_with_assets, tmp_path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _call_install_worktree_configs(project_with_assets, wt)
        dst_rules = wt / ".claude" / "rules"
        assert dst_rules.is_symlink()
        src_rules = Path(project_with_assets) / ".claude" / "rules"
        assert dst_rules.resolve() == src_rules.resolve()


class TestWriteWorkspaceSettingsUnion:
    """Unit tests for the hook-array union logic in _write_workspace_settings."""

    def test_governed_hooks_written_when_no_existing(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        _WORKSPACES._write_workspace_settings(settings)
        data = json.loads(settings.read_text())
        assert "SessionStart" in data["hooks"]
        assert "PreToolUse" in data["hooks"]

    def test_existing_unrelated_hooks_preserved(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        existing = {
            "hooks": {
                "PostToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "echo done"}]}]
            }
        }
        settings.write_text(json.dumps(existing))
        _WORKSPACES._write_workspace_settings(settings)
        data = json.loads(settings.read_text())
        assert "PostToolUse" in data["hooks"]
        assert "SessionStart" in data["hooks"]

    def test_duplicate_governed_hook_not_added_twice(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        _WORKSPACES._write_workspace_settings(settings)
        count_before = len(json.loads(settings.read_text())["hooks"]["SessionStart"])
        _WORKSPACES._write_workspace_settings(settings)
        count_after = len(json.loads(settings.read_text())["hooks"]["SessionStart"])
        assert count_before == count_after

    def test_conflicting_entry_not_duplicated(self, tmp_path):
        governed_entry = _WORKSPACES._WORKSPACE_HOOKS["hooks"]["SessionStart"][0]
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"hooks": {"SessionStart": [governed_entry]}}))
        _WORKSPACES._write_workspace_settings(settings)
        data = json.loads(settings.read_text())
        matching = [e for e in data["hooks"]["SessionStart"] if e == governed_entry]
        assert len(matching) == 1

    def test_writeWorkspaceSettings_shouldIncludeBlockOrchestratorHook_whenCreatingFreshSettings(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        _WORKSPACES._write_workspace_settings(settings)
        data = json.loads(settings.read_text())
        pre_tool_use = data["hooks"]["PreToolUse"]
        block_entries = [
            e for e in pre_tool_use
            if any("block-orchestrator-writes.py" in h.get("command", "") for h in e.get("hooks", []))
        ]
        assert len(block_entries) >= 1
        assert block_entries[0]["matcher"] == _WORKSPACES.BLOCK_ORCHESTRATOR_MATCHER

    def test_writeWorkspaceSettings_shouldPreserveBlockOrchestratorHook_whenMergingIntoExistingSettings(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        unrelated_entry = {"matcher": "Read", "hooks": [{"type": "command", "command": "python3 /some/other.py"}]}
        settings.write_text(json.dumps({"hooks": {"PreToolUse": [unrelated_entry]}}))
        _WORKSPACES._write_workspace_settings(settings)
        data = json.loads(settings.read_text())
        pre_tool_use = data["hooks"]["PreToolUse"]
        matchers = [e["matcher"] for e in pre_tool_use]
        assert "Read" in matchers
        block_entries = [
            e for e in pre_tool_use
            if any("block-orchestrator-writes.py" in h.get("command", "") for h in e.get("hooks", []))
        ]
        assert len(block_entries) >= 1

    def test_writeWorkspaceSettings_shouldNotDuplicateBlockOrchestratorHook_whenSettingsAlreadyContainIt(self, tmp_path):
        governed_pre_tool_use = _WORKSPACES._WORKSPACE_HOOKS["hooks"]["PreToolUse"]
        block_entry = next(
            e for e in governed_pre_tool_use
            if any("block-orchestrator-writes.py" in h.get("command", "") for h in e.get("hooks", []))
        )
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"hooks": {"PreToolUse": [block_entry]}}))
        _WORKSPACES._write_workspace_settings(settings)
        data = json.loads(settings.read_text())
        pre_tool_use = data["hooks"]["PreToolUse"]
        block_entries = [
            e for e in pre_tool_use
            if any("block-orchestrator-writes.py" in h.get("command", "") for h in e.get("hooks", []))
        ]
        assert len(block_entries) == 1


class TestBackupRestoreDirectories:
    """Tests for the expanded backup/restore with _BACKUP_DIRS."""

    def test_backup_creates_directory_copy(self, tmp_path):
        project = tmp_path / "project"
        (project / ".codex" / "agents").mkdir(parents=True, exist_ok=True)
        (project / ".codex" / "agents" / "test.md").write_text("# Test")
        _WORKSPACES._backup_project_files(str(project))
        backup_dir = project / ".codex.pre-workspace"
        assert backup_dir.is_dir()
        assert (backup_dir / "agents" / "test.md").read_text() == "# Test"

    def test_restore_recovers_directory(self, tmp_path):
        project = tmp_path / "project"
        (project / ".codex" / "agents").mkdir(parents=True, exist_ok=True)
        (project / ".codex" / "agents" / "test.md").write_text("# Original")
        _WORKSPACES._backup_project_files(str(project))
        (project / ".codex" / "agents" / "test.md").write_text("# Modified")
        _WORKSPACES._restore_project_files(str(project))
        assert (project / ".codex" / "agents" / "test.md").read_text() == "# Original"

    def test_backup_idempotent(self, tmp_path):
        project = tmp_path / "project"
        (project / ".codex").mkdir(parents=True)
        (project / ".codex" / "x.md").write_text("v1")
        _WORKSPACES._backup_project_files(str(project))
        (project / ".codex" / "x.md").write_text("v2")
        _WORKSPACES._backup_project_files(str(project))
        backup = project / ".codex.pre-workspace" / "x.md"
        assert backup.read_text() == "v1"

    def test_restore_removes_backup_dir(self, tmp_path):
        project = tmp_path / "project"
        (project / ".codex").mkdir(parents=True)
        (project / ".codex" / "x.md").write_text("data")
        _WORKSPACES._backup_project_files(str(project))
        _WORKSPACES._restore_project_files(str(project))
        assert not (project / ".codex.pre-workspace").exists()


class TestHookScriptRepoResolution:
    """Smoke tests for repo-root resolution in hook scripts."""

    HOOKS_DIR = REPO_ROOT / "claude" / "hooks"

    def _run_hook(self, script_name, stdin_data):
        proc = subprocess.run(
            [sys.executable, str(self.HOOKS_DIR / script_name)],
            input=json.dumps(stdin_data).encode(),
            capture_output=True,
            timeout=10,
        )
        return proc

    def test_pre_tool_hook_allows_non_governed_path(self):
        """Hook exits 0 (allow) for a tool not triggering any local deny rule."""
        proc = self._run_hook("pre-tool-hook.py", {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/some-file.txt"},
            "cwd": "/tmp",
        })
        # Exits 0 because Read is not in the deny rules and API is down → allow
        assert proc.returncode == 0

    def test_pre_tool_hook_blocks_admin_panel_curl(self):
        """Hook denies curl to admin panel."""
        proc = self._run_hook("pre-tool-hook.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "curl http://localhost:5111/api/hook/check-permission"},
            "cwd": "/tmp",
        })
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_block_orchestrator_allows_no_agent_id_outside_git(self):
        """block-orchestrator-writes allows when cwd is not inside a git repo."""
        proc = self._run_hook("block-orchestrator-writes.py", {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/somefile.py"},
            "cwd": "/tmp",
        })
        assert proc.returncode == 0

    def test_block_orchestrator_denies_main_orchestrator_file_write(self):
        """Main orchestrator (no agent_id) is denied file writes in git repo."""
        proc = self._run_hook("block-orchestrator-writes.py", {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(REPO_ROOT / "some_file.py")},
            "cwd": str(REPO_ROOT),
            # no agent_id → main orchestrator
        })
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
