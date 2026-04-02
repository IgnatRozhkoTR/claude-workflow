"""Helpers for device-scoped feature flags."""
from datetime import datetime

CODEX_PHASE1_FLAG = "codex_phase1_enabled"


def is_flag_enabled(db, flag_id, default=False):
    row = db.execute(
        "SELECT enabled FROM global_flags WHERE flag_id = ?",
        (flag_id,),
    ).fetchone()
    if row is None:
        return default
    return bool(row["enabled"])


def set_flag_enabled(db, flag_id, enabled):
    db.execute(
        "INSERT INTO global_flags (flag_id, enabled, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(flag_id) DO UPDATE SET enabled = excluded.enabled, updated_at = excluded.updated_at",
        (flag_id, 1 if enabled else 0, datetime.now().isoformat()),
    )
