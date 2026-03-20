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

# Check Python packages
python3 -c "import flask" 2>/dev/null || pip3 install flask
python3 -c "import mcp" 2>/dev/null  || pip3 install mcp
python3 -c "import flask_sock" 2>/dev/null || pip3 install flask-sock

# Check system tools
tmux -V 2>/dev/null || echo "tmux missing — install with: brew install tmux (macOS) or apt install tmux (Linux)"
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

This installs Ubuntu by default. Restart the computer when prompted. After restart, Ubuntu will launch and ask you to create a username and password.

### Step 2: Configure Claude Code to use WSL

Claude Code should run inside WSL, not in native Windows. Configure your terminal (Windows Terminal recommended) to open WSL by default, or always launch Claude Code from a WSL shell.

In Windows Terminal, set Ubuntu (WSL) as the default profile:
- Settings → Startup → Default profile → Ubuntu

### Step 3: Install dependencies inside WSL

Open the WSL terminal (Ubuntu) and run:

```bash
sudo apt update && sudo apt install -y \
  python3 python3-pip python3-venv \
  git jq sqlite3 tmux curl

pip3 install flask mcp flask-sock
```

### Step 4: Clone the repository inside WSL

**Important:** Clone inside the WSL filesystem (`~/`), NOT on the Windows mount (`/mnt/c/`). The Windows filesystem is accessible from WSL but extremely slow for git and file operations.

```bash
cd ~
git clone <your-repo-url> .claude
```

### Step 5: Project code location

Your project code should also live inside the WSL filesystem for performance:

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone <project-repo-url> my-project
```

If you must access code on the Windows side (`/mnt/c/Users/.../Projects/`), it will work but expect slower git operations and file watches.

### Step 6: Accessing the admin panel from Windows browser

The Flask server inside WSL listens on `localhost:5111`. WSL2 shares the network with Windows, so just open:

```
http://localhost:5111
```

in Chrome on Windows. No port forwarding needed.

### Step 7: Clipboard integration

For clipboard to work between WSL tmux and Windows:
- The admin panel's OSC 52 clipboard support handles this via the browser
- For direct terminal use, install `xclip` or `xsel` inside WSL:

```bash
sudo apt install -y xclip
```

Then in `~/.tmux.conf`, replace `pbcopy` with `xclip`:

```
bind -T copy-mode MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "xclip -selection clipboard"
bind -T copy-mode-vi MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "xclip -selection clipboard"
```

### After WSL setup

Continue with the **Setup Steps** section below — all steps work identically inside WSL.

### Windows-specific troubleshooting

- **`localhost:5111` not accessible from Windows browser**: Run `ip addr show eth0` in WSL to find the WSL IP. Use that IP instead (e.g., `http://172.x.x.x:5111`). Or check: `wsl hostname -I`
- **Slow git/file operations**: Move your project into the WSL filesystem (`~/Projects/`), not `/mnt/c/`
- **tmux not found**: Run `sudo apt install tmux` inside WSL
- **python3 not found**: Run `sudo apt install python3 python3-pip`
- **WSL2 taking too much memory**: Create `%UserProfile%/.wslconfig` with `[wsl2]\nmemory=4GB`

## Setup Steps

### 1. Create tmux config (if missing)

```bash
[ -f ~/.tmux.conf ] || cat > ~/.tmux.conf << 'EOF'
# Enable mouse support — scroll wheel scrolls buffer instead of sending arrow keys
set -g mouse on

# Increase scrollback buffer
set -g history-limit 10000
EOF
```

### 2. Initialize the database

```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/admin-panel/server')
from db import init_db; init_db()
print('DB initialized')
"
```

### 4. Configure MCP server in each project

For every project that uses the governed workflow, ensure `.mcp.json` exists in the project root:

```json
{
  "mcpServers": {
    "workspace": {
      "command": "python3",
      "args": ["HOMEDIR/.claude/admin-panel/server/mcp_server.py"],
      "env": {}
    }
  }
}
```

Replace `HOMEDIR` with the actual absolute home path (e.g., `/Users/username`). The path must be absolute — no `~` or `$HOME` in the JSON.

### 5. Start the admin panel server

```bash
cd ~/.claude/admin-panel/server && python3 app.py &
```

The server runs on `http://localhost:5111`. Verify:

```bash
curl -s http://localhost:5111/api/projects | python3 -m json.tool
```

### 6. Verify hook scripts work

```bash
# Test block-orchestrator-writes hook
echo '{"tool_name":"Write","tool_input":{},"cwd":"/tmp"}' | python3 ~/.claude/hooks/block-orchestrator-writes.py
# Should exit 0 (no output = allowed, since /tmp is not a git repo)

# Test pre-tool-hook (no active workspace = pass through)
echo '{"tool_name":"Edit","tool_input":{"file_path":"/tmp/test.txt"},"cwd":"/tmp"}' | python3 ~/.claude/hooks/pre-tool-hook.py
# Should exit 0
```

### 7. Verify settings.json has required entries

Check `~/.claude/settings.json` contains:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/block-orchestrator-writes.py"
          }
        ]
      },
      {
        "matcher": "Edit|Write|NotebookEdit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/pre-tool-hook.py"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/session-start.py"
          }
        ]
      }
    ]
  },
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

If `hooks` or `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` are missing, add them (merge with existing settings, don't overwrite).

## Component Inventory

| Component | Path | Purpose |
|-----------|------|---------|
| Admin panel server | `~/.claude/admin-panel/server/` | Flask app (port 5111) + SQLite DB |
| MCP server | `~/.claude/admin-panel/server/mcp_server.py` | 22+ workspace tools via stdio |
| Orchestrator block hook | `~/.claude/hooks/block-orchestrator-writes.py` | Prevents main agent from writing files in git repos |
| Phase gate hook | `~/.claude/hooks/pre-tool-hook.py` | Enforces edit/commit/push restrictions per phase |
| Session start hook | `~/.claude/hooks/session-start.py` | Registers sessions, outputs recovery context |
| Agent definitions | `~/.claude/agents/*.md` | 16 agent types (researchers, engineers, validators, reviewers) |
| Workflow skill | `~/.claude-assistant/skills/governed-workflow/SKILL.md` | Phase map, rules, MCP tool reference |
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

- **tmux**: Required for the built-in terminal feature. Install with `brew install tmux` (macOS) or `apt install tmux` (Linux). Verified by running `tmux -V`.
- **tmux config**: The admin panel sets `mouse on` per-session automatically, but for manual tmux usage, create `~/.tmux.conf`:
  ```
  set -g mouse on
  set -g history-limit 10000
  ```
- **flask-sock**: Required for WebSocket terminal support. Install with `pip3 install flask-sock`.
- **Clipboard (macOS)**: `pbcopy` — used by tmux `copy-pipe-and-cancel`
- **Clipboard (Linux/WSL)**: `xclip -selection clipboard` — replace `pbcopy` in `~/.tmux.conf`

## Optional: Telegram Integration

For remote session control via Telegram, install the multi-session Telegram channel:

1. Create a bot via [@BotFather](https://t.me/BotFather) and get the token
2. Install Bun runtime: `curl -fsSL https://bun.sh/install | bash`
3. Install the plugin: `/plugin install telegram@claude-plugins-official`
4. Configure the token: `/telegram:configure <token>`
5. Install the multi-session interceptor: `/telegram-multi-session install`
6. Enable channels in the admin panel: Configuration → Device Settings → toggle Channels on, enter `plugin:telegram@claude-plugins-official`

The admin panel automatically sets `WORKSPACE=<branch>` on every session start, so Telegram messages show which workspace they come from (e.g., `[mp-72] response text`).

## Troubleshooting

- **MCP server not connecting**: Check `.mcp.json` path is absolute and file exists. Restart Claude Code session after adding `.mcp.json`.
- **Hook not firing**: Hooks are snapshotted at session start. Restart session after changing `settings.json`.
- **DB errors**: Delete `~/.claude/admin-panel/server/admin-panel.db` and re-run step 2 to recreate.
- **Flask server not starting**: Check port 5111 is free (`lsof -i :5111`). Kill existing process or change port in `app.py`.
- **Windows: WSL not installed**: Run `wsl --install` in PowerShell as Administrator, then restart
- **Windows: Slow performance**: Ensure project is in WSL filesystem (`~/`), not Windows mount (`/mnt/c/`)
