---
name: commit-push-mr
description: Commit, push, and create merge requests in GitLab. ONLY use when the user explicitly asks to commit, push, or create an MR. Never do any of these autonomously.
---

# Commit, Push & Merge Request Workflow

## Critical Rule

**NEVER commit, push, or create a merge request unless the user explicitly asks.**
This is non-negotiable. Even if changes are ready and tested — wait for the user's instruction.

## Commit Messages

### Format

```
#TICKET-ID add work TIME description
```

### Rules

1. Starts with `#` followed by the branch/ticket ID (e.g., `#TMJ-1838`, `#MP-12`)
2. Then `add work` followed by time spent
3. Time format: `5m`, `15m`, `1h`, `1h 20m`, `2h 30m`
4. Then a lowercase description of what was done
5. **Always ask the user how much time they spent** before creating the commit

### Examples

```
#TMJ-1838 add work 5m fix tests
#TMJ-1838 add work 15m replace approaches with each other, fix tests
#TMJ-1838 add work 1h 20m implement scheduled deletion from document_photo table
#MP-12 add work 1h 20m implement the exchange 1c -> exchange server, write tests
```

### How to Commit

```bash
git add <specific files>
git commit -m "#TICKET-ID add work TIME description"
```

- Stage specific files, not `git add -A`
- Never skip hooks (`--no-verify`)
- Never amend unless explicitly asked
- Never include `Co-Authored-By` or any trailer lines in commit messages
- The ticket ID comes from the current branch name

## Push

Only push when explicitly asked. Use:

```bash
git push origin BRANCH_NAME
```

If the branch has no upstream yet:

```bash
git push -u origin BRANCH_NAME
```

## Merge Requests

### MR Title Format

```
TICKET-ID Exact YouTrack ticket name
```

**No `#` prefix** — unlike commits, MR titles do NOT start with `#`.

The title is NOT a free-form description. It is the **exact ticket name from YouTrack** — the ticket ID (tag) followed by the ticket's title verbatim. CI scripts parse this title to associate the MR with the YouTrack issue and post comments automatically. If the title doesn't match, the automation breaks.

The ticket ID (tag) always matches the branch name (e.g., branch `TMJ-1905` → tag `TMJ-1905`).

### If you don't know the ticket name

**Ask the user.** Do not guess or invent a description. Ask:
- "What is the YouTrack ticket name for this MR?" (the tag usually matches the branch)

The user always provides the ticket name when starting work on a task. If you don't have it in the conversation context, ask before creating the MR.

### Examples

```
TMJ-1905 Добавить колонки количества и единицы измерения в блок Топ-10 номенклатуры
TMJ-2181 Экспорт глобального план-факта в Эксель
TMJ-1835 Отмена задачи отправки фото если не найден заказ
```

### How to Create

Use the GitLab MCP tools (via mcp-funnel):

```
create_merge_request with:
  - project_id: "trade-management/trade-management"
  - source_branch: current branch
  - target_branch: "develop"
  - title: "TICKET-ID Exact YouTrack ticket name"
```

### MR Description

Never include `Co-Authored-By` or any trailer lines in MR descriptions.

### Target Branch

Default target is `develop` unless the user specifies otherwise.
