# Server

Flask + MCP backend for the governed workflow admin panel.

## Package layout

- `core/` — infrastructure: database, i18n, utilities, terminal management
- `advance/` — phase definitions, advancement orchestration, guards, tool permissions
- `services/` — domain CRUD services (comments, criteria, plan, scope, progress, research, etc.)
- `mcp_tools/` — MCP tool implementations (split from mcp_server.py)
- `routes/` — Flask HTTP route handlers (one Blueprint per domain)
- `migrations/` — Yoyo SQL migration scripts applied on startup via `core/db.py`
- `messages/` — i18n message catalogs (en, ru)
- `app.py` — Flask entry point
- `mcp_server.py` — MCP entry point (thin bootstrap, tools live in mcp_tools/)

Both entry points delegate to the same services — they are thin wrappers.
