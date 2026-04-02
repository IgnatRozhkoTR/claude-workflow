"""Codex feature helpers: global enablement, phase-1 launch, and review orchestration."""
from datetime import datetime
import logging

from core.db import get_db_ctx, ws_field
from core.global_flags import is_codex_enabled
from core.terminal import (
    SESSION_KIND_CODEX_REVIEW,
    build_codex_review_command,
    create_session,
    kill_session,
    notify_workspace,
    send_keys,
    session_exists,
    session_name,
    tmux_available,
)

logger = logging.getLogger(__name__)


def is_codex_review_active(db, ws):
    return is_codex_enabled(db, default=False) and bool(ws_field(ws, "codex_review_enabled", 0))


def reset_codex_review_state(workspace_id):
    with get_db_ctx() as db:
        db.execute(
            "UPDATE workspaces "
            "SET codex_review_status = 'idle', "
            "codex_review_started_at = NULL, "
            "codex_review_completed_at = NULL, "
            "codex_review_last_error = NULL "
            "WHERE id = ?",
            (workspace_id,),
        )
        db.commit()


def mark_codex_review_completed(workspace_id):
    with get_db_ctx() as db:
        db.execute(
            "UPDATE workspaces "
            "SET codex_review_status = 'completed', "
            "codex_review_completed_at = ?, "
            "codex_review_last_error = NULL "
            "WHERE id = ?",
            (datetime.now().isoformat(), workspace_id),
        )
        db.commit()


def mark_codex_review_failed(workspace_id, error):
    with get_db_ctx() as db:
        db.execute(
            "UPDATE workspaces "
            "SET codex_review_status = 'failed', "
            "codex_review_completed_at = ?, "
            "codex_review_last_error = ? "
            "WHERE id = ?",
            (datetime.now().isoformat(), error, workspace_id),
        )
        db.commit()


def stop_codex_review_for_workspace(workspace_id, reset_state=False):
    with get_db_ctx() as db:
        ws = db.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if not ws:
            return False
        name = session_name(ws["project_id"], ws["branch"], kind=SESSION_KIND_CODEX_REVIEW)

    if session_exists(name):
        kill_session(name)

    if reset_state:
        reset_codex_review_state(workspace_id)
    return True


def maybe_start_codex_review_for_workspace(workspace_id):
    with get_db_ctx() as db:
        ws = db.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if not ws:
            return False
        if ws["phase"] != "4.0":
            return False
        if not is_codex_review_active(db, ws):
            return False

        db.execute(
            "UPDATE workspaces "
            "SET codex_review_status = 'running', "
            "codex_review_started_at = ?, "
            "codex_review_completed_at = NULL, "
            "codex_review_last_error = NULL "
            "WHERE id = ?",
            (datetime.now().isoformat(), workspace_id),
        )
        db.commit()

        name = session_name(ws["project_id"], ws["branch"], kind=SESSION_KIND_CODEX_REVIEW)
        working_dir = ws["working_dir"]
        label = ws["sanitized_branch"] or ws["branch"]

    if not tmux_available():
        mark_codex_review_failed(workspace_id, "tmux is not installed")
        notify_workspace(ws, "Codex review could not start because tmux is not installed.")
        return False

    if session_exists(name):
        kill_session(name)

    try:
        create_session(name, working_dir, env={"WORKSPACE": label})
        command = build_codex_review_command(workspace_id, ws["project_id"], ws["branch"])
        if not send_keys(name, command):
            raise RuntimeError("Failed to send Codex review command to tmux")
    except Exception as exc:
        logger.warning("Failed to start Codex review for workspace %s", workspace_id, exc_info=True)
        mark_codex_review_failed(workspace_id, str(exc))
        notify_workspace(ws, "Codex review failed to start. Check the Codex review session before advancing.")
        return False

    notify_workspace(
        ws,
        "Codex review started in parallel for phase 4.0. Wait for the Codex completion notice before advancing to fixes.",
    )
    return True
