# Workspace Control

The admin panel and MCP server for the [governed workflow](../README.md). Flask web application that manages workspaces, enforces phase transitions, and provides the MCP tools agents interact with. See the root README for the workflow overview and diagram.

## Architecture

| Layer | Details |
|-------|---------|
| Backend | Flask with Blueprints (11 route modules) |
| Frontend | Vanilla HTML/CSS/JS (19 JS modules, 12 CSS modules) |
| Storage | SQLite (`server/admin-panel.db`) |
| Agent Interface | MCP server over stdio (`server/mcp_server.py`) |
| i18n | JSON message bundles (`server/messages/`) |
| Tests | pytest suite (`server/tests/`, 15 test modules) |

## Getting Started

### Prerequisites

- Python 3.10+
- `pip` or a virtual environment manager

### Install

```bash
cd ~/.claude/admin-panel
python3 -m venv .venv
source .venv/bin/activate
pip install flask mcp
```

### Run

**Option A -- launch script** (starts server in background, opens browser):

```bash
chmod +x start.sh
./start.sh
```

**Option B -- direct**:

```bash
cd server
python3 app.py
```

The server starts at http://localhost:5111. The SQLite database is created automatically on first run.

### MCP Server

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "workspace": {
      "command": "~/.claude/admin-panel/.venv/bin/python3",
      "args": ["-m", "mcp_server"],
      "cwd": "~/.claude/admin-panel/server"
    }
  }
}
```

## File Structure

```
admin-panel/
  CLAUDE.md               # Project instructions for Claude Code
  README.md               # This file
  start.sh                # Launch script (background server + browser)
  workspaces.db           # Workspace file storage (not the main DB)
  server/
    app.py                # Flask app factory, entry point
    db.py                 # SQLite schema, get_db(), auto-migrations
    helpers.py            # Shared utilities: workspace_dir(), run_git(), match_scope_pattern()
    advance_service.py    # Phase advancers, transition logic, approve/reject gates
    advance_guards.py     # Guard chain for advance validation
    criteria_validators.py # Acceptance criteria validation at execution boundaries
    mcp_server.py         # MCP server (stdio transport, 22 tools)
    i18n.py               # Internationalization loader
    messages/             # i18n JSON message bundles
    routes/
      projects.py         # Project CRUD
      workspaces.py       # Workspace + branch management, worktree creation
      state.py            # Phase, scope, plan, progress, research proving
      advance.py          # Approve/reject user gates
      comments.py         # Comment CRUD, resolve, reply, discussions
      context.py          # Workspace context, discussions, file references
      criteria.py         # Acceptance criteria CRUD + validation
      files.py            # File read, directory listing, git diff
      git_config.py       # Git config + rules management
      hooks.py            # Session start hook
      static.py           # Serves templates/ (HTML, CSS, JS, i18n)
    tests/                # pytest test suite (15 modules)
  templates/
    admin.html            # Single-page admin UI
    css/                  # 12 modular stylesheets
    js/                   # 19 vanilla JS modules
  scripts/
    update-proof-snippets.py  # Maintenance utility
```

## Admin Panel Tabs

| Tab | Visible During | Purpose |
|-----|---------------|---------|
| Pre-planning | Phases 1.0–1.4 | Review research summaries, impact analysis, and discussions. Approve/reject preparation gate (1.4). |
| Configuration | All phases | Workspace settings (previously called Dashboard). |
| Plan | Phases 2.0+ | Execution plan, sub-phases, scope, and acceptance criteria. |
| Execution | Phases 3.N.x | Per-sub-phase implementation, validation, diff viewer, and code review gate. |
| Review | Phases 4.0–4.2 | Final review issues, address & fix, and final approval gate. |

## API Overview

All workspace endpoints are scoped under `/api/ws/<project_id>/<branch>/`.

| Group | Endpoints |
|-------|-----------|
| Projects | `GET/POST /api/projects`, `DELETE /api/projects/<id>` |
| Workspaces | `GET .../branches`, `GET/POST .../workspaces`, `PUT .../archive` |
| State | `GET .../state`, `PUT .../phase`, `PUT .../scope`, `PUT .../locale` |
| Plan | `POST .../plan-status`, `POST .../restore-plan` |
| Scope | `POST .../scope-status` |
| Advance | `POST .../approve`, `POST .../reject` |
| Comments | `GET/POST .../comments`, `PUT .../comments/<id>/resolve`, `POST .../comments/<id>/reply` |
| Discussions | `POST .../discussions`, `PUT .../discussions/<id>/hide` |
| Context | `GET/PUT .../context`, `POST .../context/discussions`, `GET .../search-paths` |
| Research | `POST .../research/<id>/prove`, `DELETE .../research/<id>` |
| Criteria | `GET/POST .../criteria`, `PUT .../criteria/<id>`, `DELETE .../criteria/<id>`, `PUT .../criteria/<id>/validate` |
| Files | `GET .../file`, `GET .../files`, `GET .../diff` |
| Git Config | `GET/PUT .../git-config`, `GET/PUT .../git-rules` |
| Hooks | `POST /api/hook/session-start` |
| Progress | `GET /api/progress` |
| Modify Check | `POST .../can-modify` |

## MCP Tools

| Tool | Description |
|------|-------------|
| `workspace_get_state` | Get compact workspace state overview with summaries and counts |
| `workspace_advance` | Request phase advancement (backend decides the next phase) |
| `workspace_set_scope` | Set the phase-keyed scope map (must/may file patterns) |
| `workspace_set_plan` | Set or update the execution plan |
| `workspace_get_plan` | Get the full execution plan with all sub-phases and tasks |
| `workspace_restore_plan` | Swap current plan with the previous version |
| `workspace_post_discussion` | Raise an open discussion point (research questions, decisions) |
| `workspace_save_research` | Save structured research findings with proofs |
| `workspace_list_research` | List all research entries (id, topic, proven status) |
| `workspace_get_research` | Get full research entries by IDs including findings |
| `workspace_prove_research` | Mark a research entry as proven or rejected |
| `workspace_get_comments` | Get review comments, optionally filtered by scope |
| `workspace_post_comment` | Post a review comment on a specific file and line range |
| `workspace_resolve_comment` | Mark a review comment as resolved |
| `workspace_submit_review_issue` | Submit a code review issue with severity and location |
| `workspace_get_review_issues` | Get review issues, optionally filtered by status |
| `workspace_resolve_review_issue` | Mark a review issue as fixed, false_positive, or out_of_scope |
| `workspace_validate_review_issue` | Validate a resolved review issue (confirm fix is real) |
| `workspace_update_progress` | Record progress summary for a phase |
| `workspace_get_progress` | Get progress entries, optionally filtered by phase |
| `workspace_propose_criteria` | Propose an acceptance criterion (test, scenario, or custom) |
| `workspace_get_criteria` | Get acceptance criteria, optionally filtered by status or type |
| `workspace_update_criteria` | Update an existing criterion's description or details |
