---
name: workflow-migration
description: Install or update the governed workflow + admin panel on a device
---

# Workflow Migration

Sets up the governed multi-phase workflow on a new device.

The repository is called **governed-workflow** and can be cloned to any path on disk — `~/governed-workflow`, `/opt/governed-workflow`, or even `~/.claude` if you prefer. Examples below use `<repo>` as a placeholder for whatever path you chose.

**Platform support:** macOS (native), Linux (native), Windows (via WSL2). On Windows, the entire workflow runs inside WSL2 — the browser is the only thing that runs on the Windows side.

---

## Upgrading from System-Level Install

### What changed

The repo no longer assumes `~/.claude` as its home. Assets moved out of the dot-prefixed system directory:

| Old path | New path |
|----------|----------|
| `~/.claude/hooks/` | `<repo>/claude/hooks/` |
| `~/.claude/agents/` | `<repo>/claude/agents/` |
| `~/.claude/rules/` | `<repo>/claude/rules/` |
| `~/.claude/defaults/` | `<repo>/claude/defaults/` |
| `~/.claude/tools/` | `<repo>/claude/tools/` |
| `~/.claude/admin-panel/` | `<repo>/admin-panel/` |
| *(none)* | `<repo>/codex/` (new) |

After migration, `~/.claude` should contain only Claude Code's own config (its own `settings.json`, `CLAUDE.md`, etc.) — no governed-workflow files.

---

### Step 1: Move or clone the repo

**Option A — move in place (recommended if you have the existing DB):**
```bash
mv ~/.claude ~/governed-workflow
cd ~/governed-workflow
git worktree repair   # fixes worktree paths after the move
```

**Option B — clone fresh and bring your DB:**
```bash
git clone <your-repo-url> ~/governed-workflow
cp ~/.claude/admin-panel/server/admin-panel.db ~/governed-workflow/admin-panel/server/
```

---

### Step 2: Run the migration script

The script reads the admin-panel DB, finds all active workspaces, and updates their configuration automatically. Always do a dry-run first:

```bash
# Preview what would change:
python3 ~/governed-workflow/.claude/skills/workflow-migration/migrate.py ~/governed-workflow --dry-run

# Apply:
python3 ~/governed-workflow/.claude/skills/workflow-migration/migrate.py ~/governed-workflow
```

Replace `~/governed-workflow` with wherever you placed the repo.

---

### Step 3: Verify the repo's own hooks config

If the repo was moved (Option A), its `.claude/settings.json` uses `${CLAUDE_PROJECT_DIR}` — it should already be correct. Confirm:

```bash
grep CLAUDE_PROJECT_DIR ~/governed-workflow/.claude/settings.json
```

You should see paths like `${CLAUDE_PROJECT_DIR}/claude/hooks/pre-tool-hook.py`. If not, update them to use that form.

---

### Step 4: Clean up `~/.claude`

After the migration script completes, `~/.claude` should only hold Claude Code's own config. Verify nothing governed-workflow-related remains:

```bash
ls ~/.claude/
# Expected: CLAUDE.md  settings.json  (possibly agents/, rules/, defaults/ if you use global overrides)
# Not expected: admin-panel/  hooks/  tools/
```

Remove any leftover governed-workflow directories manually:
```bash
rm -rf ~/.claude/admin-panel ~/.claude/hooks ~/.claude/tools
```

---

### What the migration script does

Before modifying any file, the script creates a `.pre-migration` backup (e.g., `settings.json.pre-migration`). Existing backups are never overwritten, making re-runs safe.

For each active workspace the script performs these operations:

1. **`settings.json`** — rewrites hook command paths from `~/.claude/hooks/<name>` to `<new-repo>/claude/hooks/<name>` (absolute path). If the `block-orchestrator-writes.py` PreToolUse hook is missing, it is added.
2. **`.mcp.json`** — updates the `workspace` MCP server `args` to point at `<new-repo>/admin-panel/server/mcp_server.py`. Symlinked `.mcp.json` files (worktree mode) are resolved and deduplicated — the real file is only written once.
3. **Hooks** — copies files from `<repo>/claude/hooks/` to `<workspace>/.claude/hooks/`, only when the repo's copy is newer (preserves user customisations).
4. **Agents / rules / defaults** — copies missing files from `<repo>/claude/{agents,rules,defaults}/` into the workspace; never overwrites existing files (project wins). Skips `rules/` if the destination is a symlink.
5. **`.codex`** — if `.codex` is a symlink, replaces it with a real directory populated from `<repo>/codex/`. Otherwise copies only missing files (project wins).

After workspaces, the script also iterates projects directly:

6. **Project `.mcp.json`** — updates `<project>/.mcp.json` if it has old admin-panel paths. This catches projects with no active workspaces.
7. **DB** — updates `verification_steps.command` rows, replacing `~/.claude/tools/` with `${GOVERNED_WORKFLOW_TOOLS_DIR}/`.

If the new repo path resolves to `~/.claude` (in-place upgrade), hook path replacements in `settings.json` are skipped since the absolute path is unchanged. Missing hooks are still added.

---

## Prerequisites Check

```bash
python3 --version    # 3.10+
git --version
jq --version
sqlite3 --version
tmux -V

python3 -c "import flask; print('flask ok')" 2>&1
python3 -c "import mcp; print('mcp ok')" 2>&1
python3 -c "import flask_sock; print('flask_sock ok')" 2>&1
```

---

## Windows Setup (WSL2)

On Windows, the workflow runs entirely inside WSL2. The browser accesses the admin panel via `http://localhost:5111`.

**1. Install WSL2** — PowerShell as Administrator: `wsl --install`. Ubuntu installs by default; restart when prompted.

**2. Configure Claude Code** — Windows Terminal → Settings → Startup → Default profile → Ubuntu.

**3. Install system dependencies:**
```bash
sudo apt update && sudo apt install -y python3 python3-pip git jq sqlite3 tmux curl xclip unzip zip
pip3 install flask mcp flask-sock --break-system-packages
```

**4. Clone inside WSL filesystem** (NOT on `/mnt/c/` — too slow for git):
```bash
git clone <your-repo-url> ~/governed-workflow
```

**5. Configure `~/.bashrc` for non-interactive shells** — Claude Code's Bash tool runs non-interactively, so Ubuntu's default `.bashrc` exits early at the `case $-` guard. Put all exports **before** that guard:
```bash
export JAVA_HOME="/home/$USER/.sdkman/candidates/java/current"
export PATH="$JAVA_HOME/bin:$HOME/.local/bin:$PATH"
export ANTHROPIC_BASE_URL=https://your-proxy-if-any
```

**6. Install JDKs via SDKMAN:**
```bash
curl -s "https://get.sdkman.io" | bash
source ~/.sdkman/bin/sdkman-init.sh
sdk install java 21.0.7-tem && sdk default java 21.0.7-tem
```
Corporate SSL issues: create a `-k` curl wrapper in `~/.local/bin/curl`, remove after install.

**7. Git credentials** — prefer HTTPS for corporate GitHub orgs:
```bash
gh auth login && gh auth setup-git
```
Install `gh` CLI as a binary if needed (download from GitHub releases into `~/.local/bin/`).

**8. tmux config:**
```bash
cat > ~/.tmux.conf << 'EOF'
set -g mouse on
set -g history-limit 10000
bind -T copy-mode MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "xclip -selection clipboard"
EOF
```

After WSL setup, continue with **Fresh Install — Setup Steps** below (all steps work identically inside WSL).

---

## Fresh Install — Setup Steps

### 1. Clone the repo

```bash
git clone <your-repo-url> ~/governed-workflow   # or any path you prefer
cd ~/governed-workflow
```

### 2. (Optional) Export repo path

`core/paths.py` auto-detects the repo root when launched from `admin-panel/server/*`, so this is mostly a safety override:
```bash
echo 'export GOVERNED_WORKFLOW_REPO=~/governed-workflow' >> ~/.bashrc
```

### 3. Install Python dependencies

```bash
cd <repo>/admin-panel
python3 -m venv .venv
source .venv/bin/activate
pip install flask mcp flask-sock
```
Or without a venv: `pip3 install flask mcp flask-sock [--break-system-packages]`

### 4. Generate `.claude/settings.json` for the repo's own Claude session

Copy the template if it exists:
```bash
cp <repo>/claude/defaults/settings.template.json <repo>/.claude/settings.json
```

If no template exists, create `<repo>/.claude/settings.json` with this content — hook commands must use the `${CLAUDE_PROJECT_DIR}` form so they resolve regardless of where the repo is cloned:
```json
{
  "permissions": {
    "defaultMode": "bypassPermissions"
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|MultiEdit|Write|NotebookEdit|Bash",
        "hooks": [{"type": "command", "command": "python3 ${CLAUDE_PROJECT_DIR}/claude/hooks/block-orchestrator-writes.py"}]
      },
      {
        "matcher": "Edit|MultiEdit|Write|NotebookEdit|Bash",
        "hooks": [{"type": "command", "command": "python3 ${CLAUDE_PROJECT_DIR}/claude/hooks/pre-tool-hook.py"}]
      }
    ],
    "SessionStart": [
      {
        "hooks": [{"type": "command", "command": "python3 ${CLAUDE_PROJECT_DIR}/claude/hooks/session-start.py"}]
      }
    ]
  },
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "0"
  }
}
```

### 5. Initialize the database

```bash
cd <repo>/admin-panel/server
python3 -c "from db import init_db; init_db(); print('DB initialized')"
```

### 6. Configure MCP server in each project

For every project that uses the governed workflow, create `.mcp.json` in the project root. Use the absolute expanded path — no `~` or `$HOME`:
```json
{
  "mcpServers": {
    "workspace": {
      "command": "/absolute/path/to/governed-workflow/admin-panel/.venv/bin/python3",
      "args": ["-m", "mcp_server"],
      "cwd": "/absolute/path/to/governed-workflow/admin-panel/server"
    }
  }
}
```
Add `.mcp.json` to your global gitignore:
```bash
echo '.mcp.json' >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global
```

### 7. Start the admin panel

Use tmux so the server survives terminal closes:
```bash
tmux new-session -d -s admin-panel "cd <repo>/admin-panel/server && python3 app.py"
```

Convenience shell function (add before the interactive guard in `~/.bashrc`):
```bash
REPO=~/governed-workflow   # adjust to your path
ccadmin() {
  pkill -f "admin-panel/server/app.py" 2>/dev/null; sleep 1
  tmux kill-session -t admin-panel 2>/dev/null || true
  tmux new-session -d -s admin-panel "cd $REPO/admin-panel/server && python3 app.py"
  for i in 1 2 3 4 5; do
    sleep 1
    pgrep -f "admin-panel/server/app.py" > /dev/null && echo "Admin panel started on port 5111" && return
  done
  echo "Failed — check: tmux attach -t admin-panel"
}
```

### 8. Configure a project in the admin panel

Open `http://localhost:5111` and create a project pointing to your project directory.

### 9. Create a workspace

From the admin panel, create a workspace (branch). The server automatically merges the defaults from `<repo>/claude/defaults/` and `<repo>/codex/` with any project-local `.claude/` and `.codex/` overrides, then writes the merged result into the workspace's `.claude/` and `.codex/` directories.

Verify:
```bash
ls <your-project>/.claude/workspaces/<branch>/
# Should contain merged settings, rules, agents, etc.
```

---

## Verify Hooks Work

```bash
echo '{"tool_name":"Write","tool_input":{},"cwd":"/tmp"}' \
  | python3 <repo>/claude/hooks/block-orchestrator-writes.py
echo "exit: $?"  # Should be 0

echo '{"tool_name":"Edit","tool_input":{"file_path":"/tmp/test.txt"},"cwd":"/tmp"}' \
  | python3 <repo>/claude/hooks/pre-tool-hook.py
echo "exit: $?"  # Should be 0
```

---

## Component Inventory

| Component | Path | Purpose |
|-----------|------|---------|
| Admin panel server | `<repo>/admin-panel/server/` | Flask app (port 5111) + SQLite DB |
| MCP server | `<repo>/admin-panel/server/mcp_server.py` | 31 workspace tools via stdio |
| Orchestrator block hook | `<repo>/claude/hooks/block-orchestrator-writes.py` | Prevents main agent from writing files in git repos |
| Phase gate hook | `<repo>/claude/hooks/pre-tool-hook.py` | Enforces edit/commit/push restrictions per phase |
| Session start hook | `<repo>/claude/hooks/session-start.py` | Registers sessions, outputs recovery context |
| Agent definitions | `<repo>/claude/agents/` | 16 agent types (researchers, engineers, validators, reviewers) |
| Workflow skill | `<repo>/claude/skills/governed-workflow/SKILL.md` | Phase map, rules, MCP tool reference |
| Plan-preparation skill | `<repo>/claude/skills/plan-preparation/SKILL.md` | Guides phases 1.0-1.4 |
| Planning skill | `<repo>/claude/skills/planning/SKILL.md` | Guides phase 2.0 |
| Terminal support | `<repo>/admin-panel/server/terminal.py` | tmux session management for built-in terminal |
| Rules | `<repo>/claude/rules/*.md` | Coding standards, test standards, validation pipeline |
| Default git rules | `<repo>/claude/defaults/git-rules.md` | Commit/MR format rules |
| Migration skill | `<repo>/.claude/skills/workflow-migration/` | This skill — repo-only, not shipped to workspaces |

---

## Admin Panel Tabs

| Tab | Location | Purpose |
|-----|----------|---------|
| Pre-planning | Tab bar | Research summaries, impact analysis, discussions, phase 1.4 gate |
| Planning | Tab bar | Execution plan, scope, system diagrams, acceptance criteria |
| Research | Tab bar | Full research findings with proof references |
| Phase Control | Tab bar | Phase progression, approval status |
| Files | Sidebar | File browser |
| Code Changes | Sidebar | Git diff viewer |
| Configuration | Sidebar | Workspace settings, git config, Claude command |
| Review | Sidebar | Code review issues |
| Terminal | Sidebar | Built-in terminal (tmux-based) |

---

## Dependencies

- **tmux**: `apt install tmux` (Linux/WSL) or `brew install tmux` (macOS)
- **xclip** (WSL only): `apt install xclip` — clipboard between WSL tmux and Windows
- **flask-sock**: `pip3 install flask-sock [--break-system-packages]` — WebSocket terminal support
- **gh CLI**: for HTTPS git credential helper

---

## Optional: Telegram Integration

For remote session control via Telegram:

1. Create a bot via [@BotFather](https://t.me/BotFather) and get the token
2. Install Bun runtime: `curl -fsSL https://bun.sh/install | bash`
3. Install the Claude Code Telegram plugin: `/plugin install telegram@claude-plugins-official`
4. Configure the token: `/telegram:configure <token>`
5. Enable the module via the admin panel Setup page, or run `/telegram install`
6. Enable channels in admin panel: Configuration → Device Settings → toggle Channels on

---

## Troubleshooting

- **MCP server not connecting**: Check `.mcp.json` path is absolute and file exists. Restart Claude Code after adding `.mcp.json`.
- **Hook not firing**: Hooks are snapshotted at session start. Restart session after changing `settings.json`.
- **DB errors**: Delete `<repo>/admin-panel/server/admin-panel.db` and re-run Step 5 to recreate.
- **Flask server not starting**: Check port 5111 is free (`lsof -i :5111`).
- **`java`/`mvn` not found**: Exports are after the `.bashrc` interactive guard — move them above `# If not running interactively`.
- **pip3 install fails**: Add `--break-system-packages` on Ubuntu 24.04+.
- **SSH git push/fetch blocked**: Switch to HTTPS + `gh auth setup-git`.
- **`localhost:5111` not accessible on Windows**: Run `ip addr show eth0` in WSL to find its IP.
- **Slow git on Windows**: Ensure project is in WSL filesystem (`~/`), not `/mnt/c/`.
