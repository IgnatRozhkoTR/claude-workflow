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
   cp ~/.claude/skills/telegram-multi-session/server.ts ~/.claude/channels/telegram/server.ts
   ```
3. Find the telegram plugin directory:
   ```bash
   ls ~/.claude/plugins/cache/claude-plugins-official/telegram/
   ```
   Use the latest version directory.
4. Read the current `.mcp.json` in that directory and patch it to point to the custom server:
   ```json
   {
     "mcpServers": {
       "telegram": {
         "command": "bun",
         "args": ["run", "--cwd", "${CLAUDE_PLUGIN_ROOT}", "/home/user/.claude/channels/telegram/server.ts"]
       }
     }
   }
   ```
   Note: `--cwd ${CLAUDE_PLUGIN_ROOT}` is needed so bun can find node_modules (grammy, MCP SDK) from the plugin directory.
   Replace `~` with the actual expanded home directory path (use `$HOME` or `echo ~` in bash to get it).
5. Check if `~/.claude/channels/telegram/.env` exists with a `BOT_TOKEN` line. If not, tell the user:
   > Bot token not found. Create `~/.claude/channels/telegram/.env` with:
   > `BOT_TOKEN=your_token_here`
6. Confirm installation and tell the user to restart Claude Code sessions for the change to take effect.

---

### `repair`

Re-patches `.mcp.json` after a plugin update overwrites it. Does NOT re-copy
`server.ts` unless `--force` is passed.

Steps:
1. If `--force` flag is present, copy `server.ts` from skill directory to `~/.claude/channels/telegram/server.ts`
2. Run install steps 3-4 (find plugin dir, patch `.mcp.json`)
3. Confirm and tell user to restart Claude Code sessions.

---

### `update`

Deploys the latest `server.ts` from the skill directory, overwriting the currently
deployed one. Use this after editing the source file in the skill directory.

Steps:
1. Copy `~/.claude/skills/telegram-multi-session/server.ts` to `~/.claude/channels/telegram/server.ts`
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
- **Plugin updates** overwrite `.mcp.json` but not the deployed `server.ts`. Run
  `/telegram-multi-session repair` after any plugin update.

---

## Portability

This skill is self-contained. `server.ts` is bundled inside the skill directory
so no external source is needed on a new device.

To set up on a new device:
1. Transfer the `~/.claude/skills/telegram-multi-session/` directory to the new machine
2. Make sure the telegram plugin is installed (`plugin:telegram@claude-plugins-official`)
3. Run `/telegram-multi-session install`
4. Create `~/.claude/channels/telegram/.env` with `BOT_TOKEN=your_token_here` if not transferred
