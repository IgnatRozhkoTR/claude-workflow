"""Route decorators for common workspace lookup boilerplate."""
import functools

from flask import jsonify

from core.db import get_db, get_db_ctx
from core.helpers import find_workspace
from core.i18n import t


def with_workspace(fn):
    """Resolve project and workspace from URL kwargs, manage DB lifecycle.

    Extracts ``project_id`` and ``branch`` from Flask URL parameters,
    opens a DB connection, looks up the project and workspace rows,
    and passes ``db``, ``ws``, and ``project`` as keyword arguments
    to the wrapped handler.  Any remaining URL parameters (e.g.
    ``discussion_id``, ``criterion_id``) are forwarded unchanged.

    Returns 404 JSON if the project or workspace is not found.
    The DB connection is closed in a ``finally`` block regardless
    of whether the handler succeeds or raises.
    """

    @functools.wraps(fn)
    def wrapper(**kwargs):
        project_id = kwargs.pop("project_id")
        branch = kwargs.pop("branch")

        db = get_db()
        try:
            project = db.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if not project:
                return jsonify({"error": t("api.error.projectNotFound")}), 404

            ws = find_workspace(db, project_id, branch)
            if not ws:
                return jsonify({"error": t("api.error.workspaceNotFound")}), 404

            return fn(db=db, ws=ws, project=project, **kwargs)
        finally:
            db.close()

    return wrapper


def with_project(fn):
    """Decorator that loads project by project_id URL param, returns 404 if not found."""
    @functools.wraps(fn)
    def wrapper(project_id, **kwargs):
        with get_db_ctx() as db:
            project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not project:
                return jsonify({"error": t("api.error.projectNotFound")}), 404
            return fn(db=db, project=project, **kwargs)
    return wrapper
