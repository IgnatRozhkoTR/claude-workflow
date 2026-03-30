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

### `enable`

Enables the custom multi-session server. If the server is already deployed at
`~/.claude/channels/telegram/server.ts`, skip re-copying and re-installing
dependencies — just re-patch the `.mcp.json` files. Otherwise run the full
`install` flow.

Steps:
1. Check if `~/.claude/channels/telegram/server.ts` exists.
   - If it exists: skip to step 3 (re-patch only).
   - If it does not exist: run the full `install` flow (steps 1–7 of the
     `install` section), then continue with step 4 below.
2. (Install path only) After the full install flow completes, continue with step 4.
3. (Re-patch path) Unlock, patch, and re-lock `.mcp.json` in both locations:
   ```bash
   chflags nouchg ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json 2>/dev/null
   chflags nouchg ~/.claude/plugins/cache/claude-plugins-official/telegram/<version>/.mcp.json 2>/dev/null
   # Write the custom-server config to both files
   chflags uchg ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json
   chflags uchg ~/.claude/plugins/cache/claude-plugins-official/telegram/<version>/.mcp.json
   ```
4. Ensure `autoUpdate: false` is set for `claude-plugins-official` in
   `~/.claude/plugins/known_marketplaces.json`. If the key is missing or set to
   `true`, update it to `false`.
5. Confirm enable and tell the user to restart Claude Code sessions.

---

### `disable`

Disables the custom multi-session server by restoring `.mcp.json` to the
default plugin config. Does NOT delete `server.ts` or `.env`.

Steps:
1. Unlock both `.mcp.json` files:
   ```bash
   chflags nouchg ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json 2>/dev/null
   chflags nouchg ~/.claude/plugins/cache/claude-plugins-official/telegram/<version>/.mcp.json 2>/dev/null
   ```
2. Restore both `.mcp.json` files to the default plugin config:
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
3. Confirm disable. Note that `server.ts`, `.env`, and `node_modules` are
   preserved. Run `enable` to re-activate the custom server.

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

   After patching, lock both `.mcp.json` files with the immutable flag to prevent auto-sync from reverting them:
   ```bash
   chflags uchg ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json
   chflags uchg ~/.claude/plugins/cache/claude-plugins-official/telegram/0.0.4/.mcp.json
   ```
6. Set `autoUpdate: false` for `claude-plugins-official` in `~/.claude/plugins/known_marketplaces.json`.
   Read the file and update (or add) the `autoUpdate` key to `false` for that entry.
7. Check if `~/.claude/channels/telegram/.env` exists with a `BOT_TOKEN` line. If not, tell the user:
   > Bot token not found. Create `~/.claude/channels/telegram/.env` with:
   > `BOT_TOKEN=your_token_here`
8. Confirm installation and tell the user to restart Claude Code sessions for the change to take effect.

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
3. Patch `.mcp.json` in ALL locations (same as install step 5). For each location, unlock first,
   write the custom-server config, then re-lock:
   - Each version dir in `~/.claude/plugins/cache/claude-plugins-official/telegram/*/`:
     ```bash
     chflags nouchg ~/.claude/plugins/cache/claude-plugins-official/telegram/<version>/.mcp.json 2>/dev/null
     # ... patch the file ...
     chflags uchg ~/.claude/plugins/cache/claude-plugins-official/telegram/<version>/.mcp.json
     ```
   - The marketplace source:
     ```bash
     chflags nouchg ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json 2>/dev/null
     # ... patch the file ...
     chflags uchg ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json
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
2. Unlock both `.mcp.json` files before writing:
   ```bash
   chflags nouchg ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/.mcp.json 2>/dev/null
   chflags nouchg ~/.claude/plugins/cache/claude-plugins-official/telegram/<version>/.mcp.json 2>/dev/null
   ```
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
4. Confirm uninstall. Note that `server.ts` and `.env` are preserved.

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
