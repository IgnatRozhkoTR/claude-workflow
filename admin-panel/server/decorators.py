"""Route decorators for common workspace lookup boilerplate."""
import functools

from flask import jsonify

from db import get_db
from helpers import find_workspace
from i18n import t


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
