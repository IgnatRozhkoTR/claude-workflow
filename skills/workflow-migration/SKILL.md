---
name: workflow-migration
description: Install or update the governed workflow + admin panel on a device
---

# Workflow Migration

Sets up the governed multi-phase workflow on a new device. Assumes `~/.claude/` is already cloned from the repository. Covers prerequisites, database setup, hook configuration, and verification.

**Platform support:** macOS (native), Linux (native), Windows (via WSL2). On Windows, the entire workflow runs inside WSL2 — the browser is the only thing that runs on the Windows side.

## Prerequisites Check

Run these checks first. Report any failures and install what's missing.

```bash
# Required
python3 --version    # 3.10+
git --version
jq --version
sqlite3 --version
tmux -V

# Check Python packages
python3 -c "import flask; print('flask ok')" 2>&1
python3 -c "import mcp; print('mcp ok')" 2>&1
python3 -c "import flask_sock; print('flask_sock ok')" 2>&1
```

## Windows Setup (WSL2)

On Windows, the workflow runs entirely inside WSL2. The browser accesses the admin panel via localhost.

### Prerequisites

1. **Windows 10 version 2004+ or Windows 11**
2. **Administrator access** for WSL installation

### Step 1: Install WSL2

Open PowerShell as Administrator:

```powershell
wsl --install
```

This installs Ubuntu by default. Restart when prompted. After restart, Ubuntu launches and asks for a username and password.

### Step 2: Configure Claude Code to use WSL

Claude Code must run inside WSL, not native Windows. Configure Windows Terminal to open WSL by default:
- Settings → Startup → Default profile → Ubuntu

### Step 3: Install system dependencies inside WSL

```bash
sudo apt update && sudo apt install -y \
  python3 python3-pip \
  git jq sqlite3 tmux curl \
  xclip unzip zip
```

**Note:** `xclip` enables WSL↔Windows clipboard. `unzip`/`zip` are required for SDKMAN.

### Step 4: Install Python packages

Ubuntu 24.04+ uses an externally-managed Python environment. Use `--break-system-packages`:

```bash
pip3 install flask mcp flask-sock --break-system-packages
```

Installed binaries land in `~/.local/bin/`. Add to PATH (see Step 6).

### Step 5: Clone the repository inside WSL

**Important:** Clone inside the WSL filesystem (`~/`), NOT on the Windows mount (`/mnt/c/`). The Windows filesystem is slow for git operations.

```bash
cd ~
git clone <your-repo-url> .claude
```

### Step 6: Configure ~/.bashrc for non-interactive shells

Claude Code's Bash tool runs in **non-interactive mode**, which means Ubuntu's default `.bashrc` exits early at the `case $-` guard — skipping any exports after it. All environment variables must go **before** that guard.

Add this block at the very top of `~/.bashrc` (before the `# If not running interactively` comment):

```bash
# Environment — must be before interactive guard for Claude Code (non-interactive shells)
export JAVA_HOME="/home/$USER/.sdkman/candidates/java/current"
export PATH="$JAVA_HOME/bin:/path/to/maven/bin:$HOME/.local/bin:$PATH"
export ANTHROPIC_BASE_URL=https://your-proxy-if-any
```

Keep the SDKMAN init block at the **end** of `.bashrc` as required by SDKMAN — it handles interactive `sdk` commands but does NOT need to be the source of `JAVA_HOME` since we set it explicitly above.

### Step 7: Install JDKs via SDKMAN (no sudo needed)

```bash
curl -s "https://get.sdkman.io" | bash
source ~/.sdkman/bin/sdkman-init.sh
sdk install java 21.0.7-tem
sdk install java 17.0.15-tem
sdk install java 8.0.452-tem
sdk default java 21.0.7-tem
```

**Corporate proxy / SSL issues:** If `curl` fails with SSL errors, create a wrapper in `~/.local/bin/curl` that adds `-k`:
```bash
echo '#!/bin/bash\n/usr/bin/curl -k "$@"' > ~/.local/bin/curl && chmod +x ~/.local/bin/curl
```
Remove it after SDKMAN installs successfully (real `unzip`/`zip` must be installed first via apt).

### Step 8: Maven (no sudo needed)

If the project uses Maven wrapper, the `~/.m2/wrapper/dists/` cache already contains Maven after the first build. Add it to PATH explicitly in `~/.bashrc` (before the interactive guard):

```bash
export PATH="/home/$USER/.m2/wrapper/dists/apache-maven-3.8.6-bin/<hash>/apache-maven-3.8.6/bin:$PATH"
```

Alternatively install Maven via SDKMAN: `sdk install maven` (requires internet access).

### Step 9: Project code location

Copy or clone projects inside the WSL filesystem:

```bash
mkdir -p ~/Projects
# Copy from Windows mount (one-time):
rsync -a /mnt/c/Users/<winuser>/Projects/ ~/Projects/
# Or clone fresh:
git clone <repo-url> ~/Projects/my-project
```

Also copy Maven local repo if needed: `rsync -a /mnt/c/Users/<winuser>/.m2/ ~/.m2/`

### Step 10: Git credentials for GitHub

**Prefer HTTPS over SSH** for corporate GitHub orgs with IP allowlists — SSH connections go through a different network path that may be blocked even when HTTPS works.

```bash
# Install gh CLI (no sudo needed — binary install)
VERSION=$(curl -sk https://api.github.com/repos/cli/cli/releases/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])")
VER=${VERSION#v}
curl -skL "https://github.com/cli/cli/releases/download/${VERSION}/gh_${VER}_linux_amd64.tar.gz" -o /tmp/gh.tar.gz
tar -xzf /tmp/gh.tar.gz -C /tmp/
cp /tmp/gh_*/bin/gh ~/.local/bin/gh && chmod +x ~/.local/bin/gh
rm -rf /tmp/gh.tar.gz /tmp/gh_*

# Authenticate and configure as git credential helper
gh auth login
gh auth setup-git
```

Then switch all project remotes from SSH to HTTPS:
```bash
for dir in ~/Projects/*/; do
  remote=$(git -C "$dir" remote get-url origin 2>/dev/null)
  if echo "$remote" | grep -q "git@github.com:"; then
    https_url=$(echo "$remote" | sed 's|git@github.com:|https://github.com/|')
    git -C "$dir" remote set-url origin "$https_url"
  fi
done
```

### Step 11: tmux config

```bash
cat > ~/.tmux.conf << 'EOF'
set -g mouse on
set -g history-limit 10000
bind -T copy-mode MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "xclip -selection clipboard"
bind -T copy-mode-vi MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "xclip -selection clipboard"
EOF
```

### Step 12: Accessing the admin panel from Windows browser

The Flask server inside WSL listens on `localhost:5111`. WSL2 shares the network with Windows, so just open `http://localhost:5111` in Chrome on Windows. No port forwarding needed.

**Mirrored networking (optional):** To make WSL share the same IP as Windows (useful for IP allowlists), create `C:\Users\<winuser>\.wslconfig`:
```ini
[wsl2]
networkingMode=mirrored
```
Then run `wsl --shutdown` from **PowerShell on Windows** (not from inside WSL) and reopen WSL.
Note: this changes the local LAN IP but not the corporate NAT/egress IP — it won't help with GitHub org IP allowlists that block corporate egress.

### After WSL setup

Continue with the **Setup Steps** section below — all steps work identically inside WSL.

### Windows-specific troubleshooting

- **`localhost:5111` not accessible**: Run `ip addr show eth0` in WSL to find its IP. Use that instead.
- **Slow git/file operations**: Ensure project is in WSL filesystem (`~/Projects/`), not `/mnt/c/`
- **`pip3 install` fails with "externally-managed-environment"**: Add `--break-system-packages`
- **`java`/`mvn` not found in Claude Code Bash tool**: Exports are after the interactive guard — move them before `# If not running interactively` in `~/.bashrc`
- **SSH git fetch blocked by IP allowlist**: Switch remotes to HTTPS and use `gh auth setup-git`
- **SDKMAN install fails (SSL/unzip errors)**: Install `unzip zip` via apt first; use `-k` curl wrapper for SSL
- **WSL2 taking too much memory**: Add `memory=4GB` to `~/.wslconfig` under `[wsl2]`

## Setup Steps

### 1. Initialize the database

```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/admin-panel/server')
from db import init_db; init_db()
print('DB initialized')
"
```

### 2. Configure MCP server in each project

For every project that uses the governed workflow, ensure `.mcp.json` exists in the project root:

```json
{
  "mcpServers": {
    "workspace": {
      "command": "python3",
      "args": ["/home/USERNAME/.claude/admin-panel/server/mcp_server.py"],
      "env": {}
    }
  }
}
```

The path must be absolute — no `~` or `$HOME`. Add `.mcp.json` to your global gitignore:
```bash
echo '.mcp.json' >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global
```

### 3. Start the admin panel server

Use tmux so the server survives terminal closes:

```bash
tmux new-session -d -s admin-panel "cd ~/.claude/admin-panel/server && python3 app.py"
```

Add a `ccadmin` convenience function to `~/.bashrc` (before the interactive guard):

```bash
ccadmin() {
  if pgrep -f "admin-panel/server/app.py" > /dev/null; then
    echo "Stopping existing admin panel..."
    pkill -f "admin-panel/server/app.py"
    sleep 1
  fi
  tmux kill-session -t admin-panel 2>/dev/null || true
  tmux new-session -d -s admin-panel "cd ~/.claude/admin-panel/server && PATH=/home/ig/.local/bin:\$PATH python3 app.py"
  for i in 1 2 3 4 5; do
    sleep 1
    pgrep -f "admin-panel/server/app.py" > /dev/null && echo "Admin panel started on port 5111" && return
  done
  echo "Failed to start admin panel — check: tmux attach -t admin-panel"
}
```

### 4. Verify hook scripts work

```bash
echo '{"tool_name":"Write","tool_input":{},"cwd":"/tmp"}' | python3 ~/.claude/hooks/block-orchestrator-writes.py
echo "exit: $?"  # Should be 0

echo '{"tool_name":"Edit","tool_input":{"file_path":"/tmp/test.txt"},"cwd":"/tmp"}' | python3 ~/.claude/hooks/pre-tool-hook.py
echo "exit: $?"  # Should be 0
```

### 5. Verify settings.json has required entries

Check `~/.claude/settings.json` contains:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|MultiEdit|Write|NotebookEdit|Bash",
        "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/block-orchestrator-writes.py"}]
      },
      {
        "matcher": "Edit|MultiEdit|Write|NotebookEdit|Bash",
        "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/pre-tool-hook.py"}]
      }
    ],
    "SessionStart": [
      {
        "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/session-start.py"}]
      }
    ]
  },
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

## Component Inventory

| Component | Path | Purpose |
|-----------|------|---------|
| Admin panel server | `~/.claude/admin-panel/server/` | Flask app (port 5111) + SQLite DB |
| MCP server | `~/.claude/admin-panel/server/mcp_server.py` | 22+ workspace tools via stdio |
| Orchestrator block hook | `~/.claude/hooks/block-orchestrator-writes.py` | Prevents main agent from writing files in git repos |
| Phase gate hook | `~/.claude/hooks/pre-tool-hook.py` | Enforces edit/commit/push restrictions per phase |
| Session start hook | `~/.claude/hooks/session-start.py` | Registers sessions, outputs recovery context |
| Agent definitions | `~/.claude/agents/*.md` | 16 agent types (researchers, engineers, validators, reviewers) |
| Workflow skill | `~/.claude/skills/governed-workflow/SKILL.md` | Phase map, rules, MCP tool reference |
| Plan-preparation skill | `~/.claude/skills/plan-preparation/SKILL.md` | Guides phases 1.0-1.4 (assessment, research, impact analysis) |
| Planning skill | `~/.claude/skills/planning/SKILL.md` | Guides phase 2.0 (plan structure, scope, criteria) |
| Stride skill | `~/.claude/skills/stride/SKILL.md` | Lightweight workflow without admin panel |
| Terminal support | `~/.claude/admin-panel/server/terminal.py` | tmux session management for built-in terminal |
| Rules | `~/.claude/rules/*.md` | Coding standards, test standards, validation pipeline |
| Default git rules | `~/.claude/defaults/git-rules.md` | Commit/MR format rules |

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

## Dependencies

- **tmux**: `apt install tmux` (Linux/WSL) or `brew install tmux` (macOS)
- **xclip** (WSL only): `apt install xclip` — clipboard between WSL tmux and Windows
- **flask-sock**: `pip3 install flask-sock [--break-system-packages]` — WebSocket terminal support
- **unzip/zip**: `apt install unzip zip` — required for SDKMAN JDK installs
- **gh CLI**: Install via binary (see Step 10) — used as git credential helper for HTTPS

## Optional: Telegram Integration

For remote session control via Telegram, install the multi-session Telegram channel:

1. Create a bot via [@BotFather](https://t.me/BotFather) and get the token
2. Install Bun runtime: `curl -fsSL https://bun.sh/install | bash`
3. Install the plugin: `/plugin install telegram@claude-plugins-official`
4. Configure the token: `/telegram:configure <token>`
5. Install the multi-session interceptor: `/telegram-multi-session install`
6. Enable channels in the admin panel: Configuration → Device Settings → toggle Channels on, enter `plugin:telegram@claude-plugins-official`

## Troubleshooting

- **MCP server not connecting**: Check `.mcp.json` path is absolute and file exists. Restart Claude Code session after adding `.mcp.json`.
- **Hook not firing**: Hooks are snapshotted at session start. Restart session after changing `settings.json`.
- **DB errors**: Delete `~/.claude/admin-panel/server/admin-panel.db` and re-run Step 1 to recreate.
- **Flask server not starting**: Check port 5111 is free (`lsof -i :5111`). Kill existing process or change port in `app.py`.
- **`java`/`mvn` not found**: Exports are after the `.bashrc` interactive guard — move them above `# If not running interactively`.
- **pip3 install fails**: Add `--break-system-packages` on Ubuntu 24.04+.
- **SSH git push/fetch blocked**: Switch to HTTPS + `gh auth setup-git`.
- **Admin panel paste not working in browser terminal**: The terminal JS needs a `paste` event listener on the container — see `terminal.js` `_createTerminal`.
