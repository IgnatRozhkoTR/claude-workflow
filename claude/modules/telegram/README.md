# Telegram Multi-Session

Custom Telegram MCP server that replaces the default Claude Code Telegram plugin, enabling multiple sessions to share one bot with session switching and orphan recovery.

## Why

The default Telegram plugin binds to a single Claude Code session. If you run multiple sessions (different workspaces), only the last one gets messages. This server solves that by:

- Routing messages to a specific session via `/switch <name>`
- Prefixing every reply with `[workspace-name]` so you know who's talking
- Auto-detecting when the polling session dies and having another session take over

## Prerequisites

1. **Telegram bot** — create one via [@BotFather](https://t.me/BotFather)
2. **Bun runtime** — `curl -fsSL https://bun.sh/install | bash`
3. **Claude Code Telegram plugin** — `/plugin install telegram@claude-plugins-official`
4. **Plugin configured** — `/telegram:configure <bot-token>`

See the [official plugin README](https://github.com/anthropics/claude-plugins-official/blob/main/external_plugins/telegram/README.md) for initial Telegram setup (bot creation, pairing, access control).

## Install

```
/telegram-multi-session install
```

This copies `server.ts` to the Telegram channel directory (default: `${GOVERNED_WORKFLOW_TELEGRAM_STATE:-<repo>/.local/channels/telegram/}`), installs dependencies, and patches the plugin's `.mcp.json` to use the custom server.

## Usage

### From Telegram

| Command | Description |
|---------|-------------|
| `/sessions` | List active Claude Code sessions |
| `/switch <name>` | Route messages to a specific session |
| (any message) | Sent to the currently active session |

### From Claude Code

| Skill command | Description |
|---------------|-------------|
| `/telegram-multi-session status` | Check installation and active sessions |
| `/telegram-multi-session update` | Deploy latest server.ts from skill directory |
| `/telegram-multi-session repair` | Re-patch .mcp.json after plugin updates |
| `/telegram-multi-session sessions` | List sessions and clean up dead ones |

### Session naming

Sessions are named automatically from the `WORKSPACE` environment variable, which the admin panel sets to the workspace branch name (e.g., `mp-72`). Fallback chain: `$WORKSPACE` → basename of `$PWD` → random `s-<4hex>`.

### Launching with Telegram

Enable the Channels toggle in the admin panel (Configuration → Device Settings) and start/resume sessions from there. The `--channels plugin:telegram@claude-plugins-official` flag is added automatically.

## How it works

Each Claude Code session with `--channels` starts its own instance of the MCP server. Sessions register themselves in `<telegram-state>/sessions/<name>.json` with their PID (where `<telegram-state>` is `$GOVERNED_WORKFLOW_TELEGRAM_STATE` or `<repo>/.local/channels/telegram/` by default). Only one session actively polls Telegram at a time.

**Orphan detection:** Every 5 seconds, each session checks a `polling.lock` file. If the lock is stale (the polling session died), a surviving session volunteers to take over. This prevents silent message loss.

**Plugin updates** overwrite the plugin's `.mcp.json` but not the deployed `server.ts`. Run `/telegram-multi-session repair` after any plugin update.

## Portability

The skill is self-contained — `server.ts` is bundled in the skill directory. On a new device:

1. Install the Telegram plugin
2. Run `/telegram-multi-session install`
3. Create `<telegram-state>/.env` with `BOT_TOKEN=<your-token>` (default path: `<repo>/.local/channels/telegram/.env`)
