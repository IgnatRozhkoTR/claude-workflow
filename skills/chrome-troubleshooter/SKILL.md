---
name: chrome-troubleshooter
description: Diagnose and fix Claude Chrome extension connectivity issues. Use when browser automation tools fail with "extension not connected" or similar errors.
execution_mode: direct
tools_required:
  - Bash
  - Read
---

# Chrome Extension Troubleshooter

Diagnose Claude Code CLI + Chrome extension connectivity issues.

## When to Use

- `mcp__claude-in-chrome__*` tools fail
- "Browser extension is not connected" error
- Extension shows "Enabled" but tools timeout

## Quick Diagnosis (Run These)

```bash
# 1. Can native host execute?
~/.claude/chrome/chrome-native-host --version 2>&1

# 2. Is socket created?
ls -la /var/folders/**/claude-mcp-browser-bridge* 2>/dev/null

# 3. Is process running?
pgrep -fl "chrome-native-host"

# 4. What does manifest point to?
cat ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_browser_extension.json | jq -r .path

# 5. Quarantine check
xattr ~/.claude/chrome/chrome-native-host
```

## Failure Mode Decision Tree

```
Tools fail
    │
    ├── Native host --version fails?
    │   └── Gatekeeper Blockade → Fix: Remove quarantine
    │
    ├── Socket exists but no process?
    │   └── Zombie Bridge → Fix: Delete socket, restart Chrome
    │
    ├── Manifest path wrong?
    │   └── Path Rot → Fix: Edit manifest (see docs)
    │
    └── Everything looks OK?
        └── Service Worker stuck → Fix: Full Chrome restart (Cmd+Q)
```

## Fixes

### Fix 1: Remove Quarantine (Gatekeeper)
```bash
xattr -d com.apple.quarantine ~/.claude/chrome/chrome-native-host
chmod +x ~/.claude/chrome/chrome-native-host
```

### Fix 2: Delete Orphan Socket
```bash
rm /var/folders/**/claude-mcp-browser-bridge* 2>/dev/null
```

### Fix 3: Full Chrome Restart
```bash
osascript -e 'tell application "Google Chrome" to quit'
sleep 3
open -a "Google Chrome"
```

### Fix 4: Edit Manifest Path (Desktop → CLI)
Chrome extension requests `com.anthropic.claude_browser_extension` which points to Desktop by default.

```bash
# Backup
cp ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_browser_extension.json \
   ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_browser_extension.json.bak

# Edit manifest
nano ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_browser_extension.json
```

Change `path` from:
```json
"path": "/Applications/Claude.app/Contents/Helpers/chrome-native-host"
```
To:
```json
"path": "/Users/YOUR_USERNAME/.claude/chrome/chrome-native-host"
```

Then restart Chrome. To revert, restore the `.bak` file.

## Architecture

```
Claude Code CLI → MCP Server → chrome-native-host → Chrome Native Messaging → Extension
                                    ↓
                         Unix socket in /var/folders/
```

Key points:
- Extension requests native host by name: `com.anthropic.claude_browser_extension`
- Manifest at: `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/`
- Socket at: `/var/folders/.../claude-mcp-browser-bridge-{username}`

## Common Gotchas

1. **Desktop vs CLI conflict**: Only one can own the native host at a time
2. **Multiple Chromium browsers**: Each has separate NativeMessagingHosts directory:
   - Chrome: `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/`
   - Arc: `~/Library/Application Support/Arc/User Data/NativeMessagingHosts/`
   - Brave: `~/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts/`
   - Edge: `~/Library/Application Support/Microsoft Edge/NativeMessagingHosts/`
3. **After CLI update**: Native host binary may change, verify it exists
4. **Service worker caching**: Sometimes needs full browser restart, not just reload
