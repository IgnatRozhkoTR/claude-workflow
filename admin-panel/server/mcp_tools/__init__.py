"""Shared infrastructure for MCP tool modules."""
import functools
import inspect
import json
import logging
import os
import re
import sys

logger = logging.getLogger(__name__)
from datetime import datetime
from pathlib import Path

# Add server/ to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from core.db import get_db, init_db
from core.helpers import VALID_CRITERIA_TYPES, compute_phase_sequence
from core.i18n import t
from services import comment_service
from services import criteria_service
from services import discussion_service
from services import improvement_service
from services import plan_service
from services import progress_service
from services import research_service
from services import scope_service
from services import verification_service

# Initialize DB on import
init_db()


mcp = FastMCP("workspace", instructions="Workspace state management for orchestrator workflow.")


def _detect_workspace():
    """Auto-detect workspace from cwd by matching working_dir in DB. Prefers active over archived."""
    cwd = os.getcwd()
    db = get_db()
    try:
        ws = db.execute(
            "SELECT * FROM workspaces WHERE working_dir = ? ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, id DESC",
            (cwd,)
        ).fetchone()
        if ws:
            return ws, db.execute("SELECT * FROM projects WHERE id = ?", (ws["project_id"],)).fetchone()

        for parent in Path(cwd).parents:
            ws = db.execute(
                "SELECT * FROM workspaces WHERE working_dir = ? ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, id DESC",
                (str(parent),)
            ).fetchone()
            if ws:
                return ws, db.execute("SELECT * FROM projects WHERE id = ?", (ws["project_id"],)).fetchone()

        return None, None
    finally:
        db.close()


_INJECTED_PARAMS = ("ws", "project", "db", "locale")


def with_mcp_workspace(fn):
    """Decorator that injects workspace context into MCP tool functions.

    Calls _detect_workspace(), opens a DB connection, and passes (ws, project, db, locale)
    as the first positional arguments to the wrapped function.
    Returns an error dict/list if no workspace is detected.
    Closes the DB connection in a finally block. Does NOT auto-commit.
    """
    sig = inspect.signature(fn)
    exposed_params = [p for name, p in sig.parameters.items() if name not in _INJECTED_PARAMS]
    exposed_sig = sig.replace(parameters=exposed_params)

    returns_list = sig.return_annotation is list

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        ws, project = _detect_workspace()
        if not ws:
            error = {"error": t("mcp.error.noWorkspace")}
            return [error] if returns_list else error

        locale = ws["locale"] or "en"
        db = get_db()
        try:
            return fn(ws, project, db, locale, *args, **kwargs)
        finally:
            db.close()

    wrapper.__signature__ = exposed_sig
    return wrapper


# Import tool modules to register @mcp.tool handlers
from mcp_tools import state  # noqa: F401, E402
from mcp_tools import advance  # noqa: F401, E402
from mcp_tools import plan_scope  # noqa: F401, E402
from mcp_tools import research  # noqa: F401, E402
from mcp_tools import comments  # noqa: F401, E402
from mcp_tools import progress  # noqa: F401, E402
from mcp_tools import criteria  # noqa: F401, E402
from mcp_tools import improvements  # noqa: F401, E402
from mcp_tools import verification  # noqa: F401, E402
