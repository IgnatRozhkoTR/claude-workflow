# Workspace Control

Admin panel for managing scope-locked orchestrator workspaces.

## Running

```bash
python3 server/app.py
```

Runs on http://localhost:5111. DB auto-created at `server/admin-panel.db` on first run.

## Structure

```
server/
  app.py          — Flask app factory, entry point
  db.py           — SQLite schema, get_db(), migrations
  helpers.py      — Shared utilities: workspace_dir(), find_workspace(), run_git(), match_scope_pattern()
  routes/
    projects.py   — Project CRUD
    workspaces.py — Workspace + branch management
    state.py      — Phase, scope, plan endpoints
    comments.py   — Comment CRUD + resolve
    context.py    — Workspace context, discussions
    criteria.py   — Acceptance criteria CRUD
    advance.py    — Approve/reject user gates
    git_config.py — Git config + rules management
    files.py      — File read + git diff
    hooks.py      — Session hook
    static.py     — Serves templates/
  advance_service.py — Phase advancers and transition logic
  advance_guards.py  — Guard chain for advance validation
  mcp_server.py      — MCP server for agent interaction
templates/
  admin.html      — Single-page UI
  css/            — Modular stylesheets
  js/             — Vanilla JS modules
```

## Key Patterns

- `get_db()` returns sqlite3 connection with Row factory and foreign keys ON. Always close in `finally`.
- State lives in SQLite (`admin-panel.db`). No lock files. Phase, scope, plan stored as DB columns.
- `workspace_dir(project_path, branch)` resolves `<project>/.claude/workspaces/<sanitized_branch>/`
- `find_workspace(db, project_id, branch)` handles branch sanitization automatically.
- `GET /api/ws/<project>/<branch>/state` returns full workspace payload: lock, comments, plan, research, phaseHistory.

## Frontend

Vanilla JS, no framework. Global state: `LOCK_DATA`, `PLAN_DATA`, `RESEARCH_DATA`, `DIFF_DATA`, `COMMENTS`.
Comments keyed by `scope:target` in memory. Phases: 0=Init, 1.0-1.3=Assessment/Research/Proving/Impact, 2.0-2.1=Planning/Approval, 3.N.0-3.N.4=Execution sub-phases, 4.0-4.2=Review, 5=Done.
