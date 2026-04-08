"""Tests for git configuration and git rules endpoints."""
import json
import os
from pathlib import Path

from core.paths import DEFAULT_GIT_RULES


# ── GET /api/projects/<id>/git-config ──


def test_get_git_config_default_whenNoConfigFile(client, project):
    response = client.get(f"/api/projects/{project['id']}/git-config")
    assert response.status_code == 200
    data = response.get_json()
    assert data == {"provider": "local", "host": "", "token": "", "default_branch": "develop"}


def test_get_git_config_existing_whenConfigFilePresent(client, project):
    config_dir = Path(project["path"]) / ".claude"
    config_dir.mkdir(parents=True, exist_ok=True)
    config = {"provider": "gitlab", "host": "git.example.com", "token": "abc123", "default_branch": "main"}
    (config_dir / "git-config.json").write_text(json.dumps(config))

    response = client.get(f"/api/projects/{project['id']}/git-config")
    assert response.status_code == 200
    data = response.get_json()
    assert data == config


def test_get_git_config_returns404_whenProjectNotFound(client):
    response = client.get("/api/projects/nonexistent-id/git-config")
    assert response.status_code == 404
    assert "error" in response.get_json()


# ── PUT /api/projects/<id>/git-config ──


def test_save_git_config_shouldWriteFile(client, project):
    config = {"provider": "github", "host": "github.com", "token": "tok_123", "default_branch": "main"}
    response = client.put(f"/api/projects/{project['id']}/git-config", json=config)
    assert response.status_code == 200
    assert response.get_json() == {"status": "saved"}

    config_path = Path(project["path"]) / ".claude" / "git-config.json"
    assert config_path.exists()
    saved = json.loads(config_path.read_text())
    assert saved["provider"] == "github"
    assert saved["host"] == "github.com"
    assert saved["token"] == "tok_123"
    assert saved["default_branch"] == "main"


def test_save_git_config_shouldAddMcpServer_whenGitlabProvider(client, project):
    config = {"provider": "gitlab", "host": "gitlab.example.com", "token": "glpat-secret", "default_branch": "develop"}
    response = client.put(f"/api/projects/{project['id']}/git-config", json=config)
    assert response.status_code == 200

    mcp_path = Path(project["path"]) / ".mcp.json"
    assert mcp_path.exists()
    mcp = json.loads(mcp_path.read_text())
    assert "gitlab" in mcp["mcpServers"]
    gitlab_server = mcp["mcpServers"]["gitlab"]
    assert gitlab_server["command"] == "npx"
    assert "@zereight/mcp-gitlab" in gitlab_server["args"]
    assert gitlab_server["env"]["GITLAB_PERSONAL_ACCESS_TOKEN"] == "glpat-secret"
    assert gitlab_server["env"]["GITLAB_API_URL"] == "https://gitlab.example.com/api/v4"


def test_save_git_config_shouldRemoveGitlab_whenNoGitlabProvider(client, project):
    mcp_path = Path(project["path"]) / ".mcp.json"
    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    existing_mcp = {
        "mcpServers": {
            "gitlab": {"command": "npx", "args": ["-y", "@zereight/mcp-gitlab"], "env": {}},
            "other": {"command": "node", "args": ["server.js"]},
        }
    }
    mcp_path.write_text(json.dumps(existing_mcp))

    config = {"provider": "local", "host": "", "token": "", "default_branch": "develop"}
    response = client.put(f"/api/projects/{project['id']}/git-config", json=config)
    assert response.status_code == 200

    mcp = json.loads(mcp_path.read_text())
    assert "gitlab" not in mcp["mcpServers"]
    assert "other" in mcp["mcpServers"]


def test_save_git_config_returns404_whenProjectNotFound(client):
    response = client.put("/api/projects/nonexistent-id/git-config", json={"provider": "local"})
    assert response.status_code == 404
    assert "error" in response.get_json()


# ── GET /api/projects/<id>/git-rules ──


def test_get_git_rules_returnsNotConfigured_whenNoRulesFile(client, project):
    response = client.get(f"/api/projects/{project['id']}/git-rules")
    assert response.status_code == 200
    data = response.get_json()
    assert data["source"] == "not-configured"
    assert data["content"] == ""


def test_get_git_rules_returnsContent_whenProjectFileExists(client, project):
    rules_path = Path(project["path"]) / ".claude" / "rules" / "git-rules.md"
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_content = "# Git Rules\n\n- Always rebase\n- No force push"
    rules_path.write_text(rules_content)

    response = client.get(f"/api/projects/{project['id']}/git-rules")
    assert response.status_code == 200
    data = response.get_json()
    assert data["source"] == "project"
    assert data["content"] == rules_content


def test_get_git_rules_returnsSystemSource_whenSymlinkToSystemDefault(client, project):
    rules_dir = Path(project["path"]) / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_path = rules_dir / "git-rules.md"

    system_path = DEFAULT_GIT_RULES
    if not system_path.exists():
        system_path.parent.mkdir(parents=True, exist_ok=True)
        system_path.write_text("# System default git rules")

    os.symlink(str(system_path), str(rules_path))

    response = client.get(f"/api/projects/{project['id']}/git-rules")
    assert response.status_code == 200
    data = response.get_json()
    assert data["source"] == "system-default"
    assert len(data["content"]) > 0


def test_get_git_rules_returns404_whenProjectNotFound(client):
    response = client.get("/api/projects/nonexistent-id/git-rules")
    assert response.status_code == 404
    assert "error" in response.get_json()


# ── PUT /api/projects/<id>/git-rules ──


def test_save_git_rules_shouldWriteFile(client, project):
    rules_content = "# Custom Rules\n\n- Squash commits\n- Sign all commits"
    response = client.put(f"/api/projects/{project['id']}/git-rules", json={"content": rules_content})
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "saved"
    assert data["source"] == "project"

    rules_path = Path(project["path"]) / ".claude" / "rules" / "git-rules.md"
    assert rules_path.exists()
    assert not os.path.islink(rules_path)
    assert rules_path.read_text() == rules_content


def test_save_git_rules_shouldReplaceSymlink_whenSymlinkExists(client, project):
    rules_dir = Path(project["path"]) / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_path = rules_dir / "git-rules.md"

    system_path = DEFAULT_GIT_RULES
    if not system_path.exists():
        system_path.parent.mkdir(parents=True, exist_ok=True)
        system_path.write_text("# System default git rules")

    os.symlink(str(system_path), str(rules_path))
    assert os.path.islink(rules_path)

    new_content = "# Overridden Rules\n\nCustom project rules here."
    response = client.put(f"/api/projects/{project['id']}/git-rules", json={"content": new_content})
    assert response.status_code == 200

    assert not os.path.islink(rules_path)
    assert rules_path.exists()
    assert rules_path.read_text() == new_content
