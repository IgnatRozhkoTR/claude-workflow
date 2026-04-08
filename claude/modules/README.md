# Modules

Self-contained feature packages that extend the governed workflow. Each module is an independent directory containing a `SKILL.md` and any supporting files it needs.

## Directory Structure

```
modules/
  <module-id>/
    SKILL.md          # Skill definition with install/status/repair instructions
    <other files>     # Scripts, configs, server code, etc.
```

The admin panel scans this directory to discover available modules. Any subdirectory containing a `SKILL.md` is treated as a module.

## Enabling Modules

Two ways to enable a module:

- **Setup wizard** — accessible from the project selector page in the admin panel. Guides through module selection and installation in one session.
- **Modules card** — on the admin panel dashboard. Shows all discovered modules with their status; toggle to install or disable.

Both methods launch Claude Code in an embedded terminal and follow the module's `SKILL.md` install instructions.

## Creating a Module

1. Create a subdirectory under `<repo>/claude/modules/<module-id>/`
2. Add a `SKILL.md` with at minimum an `install` section and a `status` section
3. Add any supporting files the module needs (scripts, server code, configs)

The `SKILL.md` must follow the standard skill frontmatter format and define dispatch commands (`install`, `status`, `repair`, `uninstall`) that Claude Code will execute.

## Current Modules

| Module | Description |
|--------|-------------|
| `telegram` | Multi-session Telegram bot server. Allows multiple Claude Code sessions to share one Telegram bot with `/switch` and `/sessions` commands. See [telegram/SKILL.md](telegram/SKILL.md). |
