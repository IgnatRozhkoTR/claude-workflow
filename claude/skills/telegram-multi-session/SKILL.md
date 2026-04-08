---
name: telegram-multi-session
description: Install, repair, and manage the multi-session Telegram channel server that allows switching between Claude Code sessions from Telegram
user_invocable: true
tools_required:
  - Bash
  - Read
  - Edit
  - Write
---

# /telegram-multi-session — Multi-Session Telegram Channel Manager

Manages the custom multi-session Telegram server that replaces the default plugin
server. This skill is **self-contained**: `server.ts` lives inside the skill
directory and is deployed by the `install` command.

Throughout this skill, `<tg-state>` refers to the Telegram state directory.
Resolve it at runtime:
```bash
TG_STATE="${GOVERNED_WORKFLOW_TELEGRAM_STATE:-$(python3 -c 'from core.paths import REPO_ROOT; print(REPO_ROOT)')/.local/channels/telegram}"
```
If `GOVERNED_WORKFLOW_TELEGRAM_STATE` is not set, the default is `<repo>/.local/channels/telegram/`.

The source `server.ts` lives inside this skill directory and is deployed to `<tg-state>/server.ts`.

Arguments passed: (check the args variable from the skill invocation)

---

## Dispatch on arguments

Parse the arguments (space-separated). If empty or unrecognized, run status.

---

### No args — `status`

1. Check if custom server exists at `<tg-state>/server.ts`
2. Check if `.mcp.json` in the telegram plugin directory is patched (points to custom server vs default)
3. Check if `<tg-state>/.env` exists and contains `BOT_TOKEN`
4. Read all files from `<tg-state>/sessions/`, check PID liveness, list active sessions
5. Report overall status: installed/not installed, patched/not patched, token present/missing, active sessions

---

### `install`

1. Create `<tg-state>/` if it doesn't exist
2. Copy `server.ts` from the skill directory to `<tg-state>/server.ts`:
   ```bash
   cp <skill-dir>/server.ts "$TG_STATE/server.ts"
   ```
3. Install dependencies alongside the server:
   ```bash
   cp ~/.claude/plugins/cache/claude-plugins-official/telegram/$(ls ~/.claude/plugins/cache/claude-plugins-official/telegram/)/package.json "$TG_STATE/"
   cd "$TG_STATE" && bun install --no-summary
   ```
   Note: Bun resolves node_modules relative to the file location, not `--cwd`. Installing dependencies here ensures the server can find grammy and @modelcontextprotocol/sdk.
4. Find the telegram plugin directory:
   ```bash
   ls ~/.claude/plugins/cache/claude-plugins-official/telegram/
   ```
   Use the latest version directory.
5. Read the current `.mcp.json` in that directory and patch it to point to the custom server:
   ```json
   {
     "mcpServers": {
       "telegram": {
         "command": "bun",
         "args": ["run", "/absolute/path/to/tg-state/server.ts"]
       }
     }
   }
   ```
   Use the actual expanded path to `<tg-state>/server.ts` (no `~` or env vars — bun requires an absolute literal path).
6. Check if `<tg-state>/.env` exists with a `BOT_TOKEN` line. If not, tell the user:
   > Bot token not found. Create `<tg-state>/.env` with:
   > `BOT_TOKEN=your_token_here`
7. Confirm installation and tell the user to restart Claude Code sessions for the change to take effect.

---

### `repair`

Re-patches `.mcp.json` after a plugin update overwrites it. Does NOT re-copy
`server.ts` unless `--force` is passed.

Steps:
1. If `--force` flag is present, copy `server.ts` from skill directory to `<tg-state>/server.ts`
2. If `<tg-state>/node_modules` is missing, re-run bun install:
   ```bash
   cd "$TG_STATE" && bun install --no-summary
   ```
3. Run install steps 4-5 (find plugin dir, patch `.mcp.json`)
4. Confirm and tell user to restart Claude Code sessions.

---

### `update`

Deploys the latest `server.ts` from the skill directory, overwriting the currently
deployed one. Use this after editing the source file in the skill directory.

Steps:
1. Copy `<skill-dir>/server.ts` to `<tg-state>/server.ts`
2. Confirm the update. Remind user to restart Claude Code sessions.

---

### `uninstall`

Restore `.mcp.json` to the default plugin config. Does NOT delete the custom server.

Steps:
1. Find the telegram plugin directory
2. Restore `.mcp.json` to the default:
   ```json
   {
     "mcpServers": {
       "telegram": {
         "command": "bun",
         "args": ["run", "--cwd", "${CLAUDE_PLUGIN_ROOT}", "--shell=bun", "--silent", "start"]
       }
     }
   }
   ```
3. Confirm uninstall. Note that `server.ts` and `.env` are preserved.

---

### `sessions`

1. Read all files from `<tg-state>/sessions/`
2. For each, parse JSON and check if PID is still alive (`kill -0 <pid>`)
3. Display: session name, PID, uptime, alive/dead status
4. Clean up dead session files (delete them)

---

### `name <new-name>`

Set the session name for the CURRENT session by calling the `set_session_name` MCP tool.
Note: this only works if the multi-session server is running in this session.
The tool is available as `mcp__plugin_telegram_telegram__set_session_name`.

---

## How it works

- **Session names** default to the basename of the working directory (PWD) where
  Claude Code was launched. The `WORKSPACE` environment variable overrides this
  (`WORKSPACE=work claude --channels ...`). If neither is set, a random `s-<4hex>`
  name is used. Names can also be changed at runtime via `set_session_name` or
  `/telegram-multi-session name <name>`.
- **Outbound replies** are automatically prefixed with `[session-name]` so the
  user can tell which Claude Code session is responding.
- **From Telegram**: send `/sessions` to list active sessions, `/switch <name>` to
  route incoming messages to a specific session.
- **MCP tools** available in each session: `claim_channel`, `channel_status`,
  `set_session_name`.
- **Dependencies**: Each deployed server has its own `node_modules` alongside it.
  This is required because bun resolves modules relative to the file location, not
  the working directory.
- **Plugin updates** overwrite `.mcp.json` but not the deployed `server.ts`. Run
  `/telegram-multi-session repair` after any plugin update.

---

## Troubleshooting

- **`Cannot find module '@modelcontextprotocol/sdk/server/index.js'`**: Dependencies are missing. Run:
  ```bash
  cd "$TG_STATE" && bun install --no-summary
  ```
  This happens if the install step was skipped or node_modules was deleted.
- **Bot stops responding but sessions show as alive**: If the session that was
  actively polling Telegram dies or loses its connection, other sessions may sit
  idle with no one listening to Telegram updates. Since v2, the server includes
  orphan detection — every 5 seconds each session checks if anyone is polling and
  auto-volunteers if not. If you're on an older version, run
  `/telegram-multi-session update` to deploy the fix. As a manual workaround, use
  the `claim_channel` MCP tool from any live session, or restart a session.

---

## Portability

This skill is self-contained. `server.ts` is bundled inside the skill directory
so no external source is needed on a new device.

To set up on a new device:
1. The skill ships with the repo at `<repo>/claude/skills/telegram-multi-session/`
2. Make sure the telegram plugin is installed (`plugin:telegram@claude-plugins-official`)
3. Run `/telegram-multi-session install` — this also installs dependencies automatically
4. Create `<tg-state>/.env` with `BOT_TOKEN=your_token_here` if not transferred

Note: `node_modules/`, `bun.lock`, and `package.json` in `<tg-state>/` are NOT
transferred between devices — they are regenerated by the install command.
