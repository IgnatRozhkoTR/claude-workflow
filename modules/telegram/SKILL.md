---
name: telegram
description: Install, repair, and manage the multi-session Telegram channel server that allows switching between Claude Code sessions from Telegram
user_invocable: true
tools_required:
  - Bash
  - Read
  - Edit
  - Write
---

> This module can be configured via the admin panel's Setup page.

# /telegram-multi-session — Multi-Session Telegram Channel Manager

Manages the custom multi-session Telegram server that replaces the default plugin
server. This skill is **self-contained**: `server.ts` lives inside the skill
directory and is deployed by the `install` command.

The deployed server lives at `~/.claude/channels/telegram/server.ts` and supports
multiple Claude Code sessions sharing one Telegram bot, with `/switch` and
`/sessions` commands from Telegram.

Arguments passed: (check the args variable from the skill invocation)

---

## Dispatch on arguments

Parse the arguments (space-separated). If empty or unrecognized, run status.

---

### No args — `status`

1. Check if custom server exists at `~/.claude/channels/telegram/server.ts`
2. Check if `.mcp.json` in the telegram plugin directory is patched (points to custom server vs default)
3. Check if `~/.claude/channels/telegram/.env` exists and contains `BOT_TOKEN`
4. Read all files from `~/.claude/channels/telegram/sessions/`, check PID liveness, list active sessions
5. Report overall status: installed/not installed, patched/not patched, token present/missing, active sessions

---

### `install`

1. Create `~/.claude/channels/telegram/` if it doesn't exist
2. Copy `server.ts` from the skill directory to `~/.claude/channels/telegram/server.ts`:
   ```bash
   cp ~/.claude/modules/telegram/server.ts ~/.claude/channels/telegram/server.ts
   ```
3. Install dependencies alongside the server:
   ```bash
   cp ~/.claude/plugins/cache/claude-plugins-official/telegram/$(ls ~/.claude/plugins/cache/claude-plugins-official/telegram/)/package.json ~/.claude/channels/telegram/
   cd ~/.claude/channels/telegram && bun install --no-summary
   ```
   Note: Bun resolves node_modules relative to the file location, not `--cwd`. Installing dependencies here ensures the server can find grammy and @modelcontextprotocol/sdk.
4. Find the telegram plugin directory:
   ```bash
   ls ~/.claude/plugins/cache/claude-plugins-official/telegram/
   ```
   Use the latest version directory.
5. Patch `.mcp.json` in ALL locations to point to the custom server. There are multiple copies that must all be patched:
   - **Cache version**: `~/.claude/plugins/cache/claude-plugins-official/telegram/<version>/.mcp.json` (for each version dir)
   - **Marketplace source**: `~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json`

   All must be set to:
   ```json
   {
     "mcpServers": {
       "telegram": {
         "command": "bun",
         "args": ["run", "/home/user/.claude/channels/telegram/server.ts"]
       }
     }
   }
   ```
   Replace `/home/user` with the actual home directory path (use `$HOME` or `echo ~` in bash to get it).

   **Important**: The marketplace source copy is what Claude Code actually reads. If only the cache copy is patched, the fix won't take effect. Always patch both.

   After patching, make the marketplace `.mcp.json` read-only to prevent auto-sync from reverting it:
   ```bash
   chmod a-w ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json
   ```
6. Check if `~/.claude/channels/telegram/.env` exists with a `BOT_TOKEN` line. If not, tell the user:
   > Bot token not found. Create `~/.claude/channels/telegram/.env` with:
   > `BOT_TOKEN=your_token_here`
7. Confirm installation and tell the user to restart Claude Code sessions for the change to take effect.

---

### `repair`

Re-patches `.mcp.json` in ALL locations after a plugin update overwrites them.
Does NOT re-copy `server.ts` unless `--force` is passed.

Steps:
1. If `--force` flag is present, copy `server.ts` from `~/.claude/modules/telegram/server.ts` to `~/.claude/channels/telegram/server.ts`
2. If `~/.claude/channels/telegram/node_modules` is missing, re-run bun install:
   ```bash
   cd ~/.claude/channels/telegram && bun install --no-summary
   ```
3. Patch `.mcp.json` in ALL locations (same as install step 5):
   - Each version dir in `~/.claude/plugins/cache/claude-plugins-official/telegram/*/`
   - The marketplace source: first make writable (`chmod u+w`), patch, then make read-only again (`chmod a-w`):
     ```bash
     chmod u+w ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json
     # ... patch the file ...
     chmod a-w ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json
     ```
4. Confirm and tell user to restart Claude Code sessions.

---

### `update`

Deploys the latest `server.ts` from the skill directory, overwriting the currently
deployed one. Use this after editing the source file in the skill directory.

Steps:
1. Copy `~/.claude/modules/telegram/server.ts` to `~/.claude/channels/telegram/server.ts`
2. Confirm the update. Remind user to restart Claude Code sessions.

---

### `uninstall`

Restore `.mcp.json` to the default plugin config in ALL locations. Does NOT delete the custom server.

Steps:
1. Find all telegram plugin directories (cache versions + marketplace source)
2. Make marketplace `.mcp.json` writable first: `chmod u+w ~/.claude/plugins/marketplaces/.../external_plugins/telegram/.mcp.json`
3. Restore `.mcp.json` in each location to the default:
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

1. Read all files from `~/.claude/channels/telegram/sessions/`
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
- **Multiple `.mcp.json` locations**: The plugin has `.mcp.json` in both the cache
  (`~/.claude/plugins/cache/.../telegram/<version>/`) AND the marketplace source
  (`~/.claude/plugins/marketplaces/.../external_plugins/telegram/`). Claude Code
  reads the marketplace source copy, so it MUST be patched. The repair command
  patches all locations automatically.

---

## Troubleshooting

- **`Cannot find module '@modelcontextprotocol/sdk/server/index.js'`**: Dependencies are missing. Run:
  ```bash
  cd ~/.claude/channels/telegram && bun install --no-summary
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
1. Transfer the `~/.claude/skills/telegram-multi-session/` directory to the new machine
2. Make sure the telegram plugin is installed (`plugin:telegram@claude-plugins-official`)
3. Run `/telegram-multi-session install` — this also installs dependencies automatically
4. Create `~/.claude/channels/telegram/.env` with `BOT_TOKEN=your_token_here` if not transferred

Note: `node_modules/`, `bun.lock`, and `package.json` in `~/.claude/channels/telegram/` are NOT
transferred between devices — they are regenerated by the install command.
