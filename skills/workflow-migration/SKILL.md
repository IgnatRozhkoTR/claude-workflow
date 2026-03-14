---
name: workflow-migration
description: Install or update the governed workflow + admin panel on a device
user_invocable: true
---

# Workflow Migration

Install, update, or verify the governed workflow system on a device. This skill is designed to work on any fresh macOS laptop.

## When to Use

- Setting up a new device from scratch
- Pulling updates after changes to the admin panel
- Verifying installation integrity
- Troubleshooting broken hooks, MCP, or admin panel

## System Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Admin Panel (Flask) | `~/.claude/admin-panel/` | Web UI for workspace management |
| MCP Server | `~/.claude/admin-panel/server/mcp_server.py` | Agent-workspace state bridge (stdio) |
| Hooks | `~/.claude/hooks/` | Session reminder, prompt hint, phase enforcement |
| Governed Workflow Skill | `~/.claude/skills/governed-workflow/` | Orchestrator instructions |
| Agent Definitions | `~/.claude/agents/` | Sub-agent role definitions |

## Prerequisites

Verify each before proceeding. Install any that are missing.

| Dependency | Check Command | Install (macOS) |
|------------|---------------|-----------------|
| Python 3.10+ | `python3 --version` | `brew install python@3.12` |
| pip | `pip3 --version` | Comes with Python |
| Node.js 18+ & npm | `node --version && npm --version` | `brew install node` |
| jq | `jq --version` | `brew install jq` |
| sqlite3 | `sqlite3 --version` | Pre-installed on macOS |
| Git | `git --version` | `brew install git` |
| curl | `curl --version` | Pre-installed on macOS |
| Claude Code CLI | `claude --version` | `npm install -g @anthropic-ai/claude-code` |

## Fresh Installation

### Step 1: Install system dependencies

```bash
# macOS — install missing tools
brew install jq python@3.12 node  # skip if already installed
```

### Step 2: Create Python virtual environment

Modern macOS (Homebrew Python 3.12+) is externally managed and blocks direct `pip install`. Use a virtual environment instead — this works universally on all platforms.

```bash
python3 -m venv ~/.claude/admin-panel/.venv
~/.claude/admin-panel/.venv/bin/pip install flask "mcp[cli]"
```

The admin panel's `start.sh` automatically detects and uses this venv.

### Step 3: Verify admin panel exists

```bash
ls ~/.claude/admin-panel/server/app.py
```

If missing, the admin panel repository needs to be cloned or copied to `~/.claude/admin-panel/`. The admin panel is NOT a public package — it must be transferred from an existing installation.

### Step 4: Install hook scripts

Three scripts must exist in `~/.claude/hooks/` and be executable:

```bash
chmod +x ~/.claude/hooks/session-start.sh
chmod +x ~/.claude/hooks/user-prompt-submit.sh
chmod +x ~/.claude/hooks/pre-tool-hook.sh
```

**`session-start.sh`** — Registers session with Flask server, prints governed workflow reminder to agent on every session start (including after compaction).

**`user-prompt-submit.sh`** — Prints a short governed workflow hint on every user message.

**`pre-tool-hook.sh`** — Phase-gated enforcement:
- Blocks Edit/Write outside implementation phases (4.N.0, 4.N.2, 5.1)
- Enforces file scope against active_scope from DB
- Blocks git commit outside commit phases (4.N.4)
- Blocks git push/PR outside phase 6
- Blocks curl to admin-only approval/rejection endpoints
- Allows workspace metadata files unconditionally
- Requires `jq` and `sqlite3` CLI tools

### Step 5: Configure `~/.claude/settings.json`

Merge these entries into the existing settings file. Do NOT overwrite — merge the `hooks` section:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|Bash|mcp__.*gitlab.*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/pre-tool-hook.sh"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/session-start.sh"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/user-prompt-submit.sh"
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

### Step 6: Configure `~/.claude/settings.local.json`

Ensure the governed-workflow skill is permitted. Add to the `permissions.allow` array:

```json
"Skill(governed-workflow)"
```

### Step 7: Configure MCP for the project

Create `.mcp.json` in the project root. The path MUST be absolute:

```json
{
  "mcpServers": {
    "workspace": {
      "command": "/Users/USERNAME/.claude/admin-panel/.venv/bin/python3",
      "args": ["/Users/USERNAME/.claude/admin-panel/server/mcp_server.py"],
      "env": {}
    }
  }
}
```

Replace `/Users/USERNAME` with the actual home directory path (`echo $HOME`).

For GitLab projects, the admin panel auto-generates `.mcp-funnel.json` (MCP Funnel — filters GitLab tools, ~90% token reduction) and routes `.mcp.json` through it during workspace creation. The funnel template lives at `~/.claude/defaults/.mcp-funnel.json`.

### Step 8: Set up shell alias (recommended)

Add to `~/.zshrc` (or `~/.bashrc`):

```bash
alias ccadmin='bash ~/.claude/admin-panel/start.sh'
```

Then reload: `source ~/.zshrc`

After this, typing `ccadmin` in any terminal will restart the admin panel and open it in the browser.

### Step 9: Start admin panel

```bash
bash ~/.claude/admin-panel/start.sh
# Or, if alias is set up:
ccadmin
```

This kills any existing instance, starts the Flask server on port 5111, and opens the browser.

### Step 10: Register the project

1. Open the admin panel at http://localhost:5111
2. Click "Add Project"
3. Enter the project path (absolute) and a display name
4. Create a workspace for the branch you want to work on

### Step 11: Verify

Run through this checklist:

- [ ] `curl -s http://localhost:5111/api/projects` — returns JSON array
- [ ] `ls -la ~/.claude/hooks/` — all three scripts present and executable
- [ ] `jq '.hooks' ~/.claude/settings.json` — shows all three hook entries
- [ ] `cat .mcp.json` (in project root) — shows workspace MCP server with absolute path
- [ ] `~/.claude/admin-panel/.venv/bin/python3 -c "from mcp.server.fastmcp import FastMCP; print('OK')"` — prints OK
- [ ] Start a new Claude Code session — should see the governed workflow reminder
- [ ] Run `/governed-workflow` — skill loads without error

## Updating an Existing Installation

1. Pull latest admin panel changes (if tracked in git):
   ```bash
   cd ~/.claude/admin-panel && git pull
   ```

2. Re-install Python dependencies (in venv):
   ```bash
   ~/.claude/admin-panel/.venv/bin/pip install --upgrade flask "mcp[cli]"
   ```

   If the venv doesn't exist yet (migrating from an older installation):
   ```bash
   python3 -m venv ~/.claude/admin-panel/.venv
   ~/.claude/admin-panel/.venv/bin/pip install flask "mcp[cli]"
   ```

3. Compare and update hook files if changed.

4. Restart server:
   ```bash
   ccadmin  # or: bash ~/.claude/admin-panel/start.sh
   ```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port 5111 in use | `lsof -ti :5111 \| xargs kill -9` |
| DB locked or corrupted | Stop server, `rm ~/.claude/admin-panel/server/admin-panel.db`, restart (projects need re-registration) |
| Hook not firing | Check `settings.json` has all entries; verify `chmod +x` on scripts |
| MCP tools unavailable | Check `.mcp.json` path is absolute; restart Claude Code session |
| pre-tool-hook errors | Verify `jq` and `sqlite3` are installed |
| "No workspace found" from MCP | Register project + create workspace in admin panel |
| Phase stuck | Use admin panel UI to inspect; may need manual DB update via `sqlite3` |
| `ccadmin` not found | Run `source ~/.zshrc` or add the alias manually |
| Flask import error | Run `~/.claude/admin-panel/.venv/bin/pip install flask` |
| MCP import error | Run `~/.claude/admin-panel/.venv/bin/pip install "mcp[cli]"` |
| pip: externally-managed-environment | Use the venv: `python3 -m venv ~/.claude/admin-panel/.venv` then install in venv |

## Windows Support (TBD)

Windows is not yet supported. The following would need to be addressed:

- **Hook scripts**: Rewrite all three `.sh` hooks as PowerShell (`.ps1`) or batch (`.cmd`) scripts
- **Shell alias**: Replace with a `.cmd` file in PATH or a PowerShell function in `$PROFILE`
- **`open` command**: Replace with `start http://localhost:5111`
- **`lsof`**: Replace with `netstat -ano | findstr :5111` and `taskkill /PID`
- **`sqlite3` CLI**: May need manual installation (not pre-installed on Windows)
- **`jq`**: Install via `choco install jq` or `scoop install jq`
- **Path separators**: All paths use `/` — may need `\` on Windows
- **`nohup`**: Replace with `Start-Process` in PowerShell
- **settings.json hook commands**: Change `bash` to `powershell` or `cmd`

Until Windows support is implemented, the workflow can only run on macOS (and likely Linux with minor adjustments).

## Adding a New Agent

To integrate a new agent into the governed workflow system:

### 1. Create the agent file

Create `~/.claude/agents/<name>.md` with YAML frontmatter and dual-mode structure:

```markdown
---
name: my-new-researcher
description: One-line description of what this agent does
tools: Glob, Grep, LS, Read, Write
model: sonnet
color: blue
---

<!-- Base section: works standalone without MCP/workflow -->
<rules>...</rules>
<approach>...</approach>
<constraints>...</constraints>

<!-- Governed workflow section: active when MCP tools are available -->
<governed-workflow>
When working within the governed workflow (MCP tools available):

1. Call `workspace_get_state` to understand the current phase and context
2. Do your work
3. Call `workspace_save_research` with findings (if researcher)

Each finding proof: { "type": "...", ... }
</governed-workflow>
```

The base section works for standalone use. The `<governed-workflow>` section activates when the agent has access to MCP tools in a workspace.

### 2. Register the agent

The agent is automatically available via Claude Code's `Agent` tool once the file exists in `~/.claude/agents/` (or `~/.claude-assistant/agents/`). The `name` in frontmatter becomes the `subagent_type` value.

### 3. Define proof type (researchers only)

If the agent is a researcher, define its proof format in the `<governed-workflow>` section. Use an existing proof type when possible:

| Proof Type | Used By | Key Fields |
|-----------|---------|------------|
| `code` | code-researcher, senior-code-researcher | `file`, `line_start/end`, `snippet_start/end` (server reads file) |
| `web` | web-researcher, ui-researcher | `url`, `title`, `quote` (agent-provided text) |
| `diff` | diff-researcher | `commit`, `file` (optional), `description` |

If a new proof type is needed:
1. Add it to `workspace_save_research` tool description in `server/mcp_server.py`
2. Add rendering logic in `templates/js/research.js` (new branch in the proof type dispatcher)
3. Add CSS in `templates/css/research.css` if the new type needs distinct styling

### 4. Update the governed workflow skill (if needed)

If the new agent participates in the phase flow (e.g., a new kind of researcher in phase 2.0), update `~/.claude/skills/governed-workflow/SKILL.md` to mention it in the relevant phase section.

Non-researcher agents (engineers, validators) typically don't need MCP tools — they receive tasks from the orchestrator and report back via messages.

---

## What This Skill Does NOT Cover

- Agent definitions (`~/.claude/agents/`) — managed separately
- Project-specific rules (`.rules/` directory) — project-specific
- The governed-workflow skill content — that's a separate skill (`/governed-workflow`)
- Syncing the SQLite DB between devices — each device has its own project registry
- Creating or managing workspaces — done via admin panel UI
