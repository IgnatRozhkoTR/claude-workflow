# Core

Foundation layer — no business logic, no domain imports. Everything else depends on core, core depends on nothing in the server package.

- `db.py` — SQLite connection, schema DDL, migrations
- `helpers.py` — path utilities, git subprocess wrapper, scope pattern matching
- `i18n.py` — translation with locale fallback (message files live in `server/messages/`)
- `phase.py` — Phase value object (comparable, ordinal dotted-string)
- `terminal.py` — tmux session management, PTY-WebSocket bridge
- `decorators.py` — Flask route decorators (`with_workspace`, `with_project`)
