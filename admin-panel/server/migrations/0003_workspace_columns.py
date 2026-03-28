"""
Add columns to the workspaces table that were introduced after the initial schema.
Each addition checks for column existence first (idempotent).
"""
from yoyo import step

_NEW_COLUMNS = [
    ("status", "TEXT NOT NULL DEFAULT 'active'"),
    ("phase", "TEXT NOT NULL DEFAULT '0'"),
    ("scope_json", "TEXT DEFAULT '{}'"),
    ("plan_json", "TEXT DEFAULT '{\"description\":\"\",\"systemDiagram\":\"\",\"execution\":[]}'"),
    ("commit_message", "TEXT"),
    ("gate_nonce", "TEXT"),
    ("source_branch", "TEXT"),
    ("locale", "TEXT NOT NULL DEFAULT 'en'"),
    ("ticket_id", "TEXT"),
    ("ticket_name", "TEXT"),
    ("context_text", "TEXT"),
    ("scope_status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("plan_status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("context_refs_json", "TEXT DEFAULT '[]'"),
    ("prev_plan_json", "TEXT"),
    ("prev_scope_json", "TEXT"),
    ("prev_phase", "TEXT"),
    ("prev_plan_status", "TEXT"),
    ("prev_scope_status", "TEXT"),
    ("claude_command", "TEXT NOT NULL DEFAULT 'claude'"),
    ("skip_permissions", "INTEGER NOT NULL DEFAULT 1"),
    ("impact_analysis_json", "TEXT"),
    ("restrict_to_workspace", "INTEGER NOT NULL DEFAULT 1"),
    ("allowed_external_paths", "TEXT NOT NULL DEFAULT '/tmp/'"),
    ("channels", "TEXT DEFAULT ''"),
    ("yolo_mode", "INTEGER NOT NULL DEFAULT 0"),
]


def apply_step(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(workspaces)")
    existing = {row[1] for row in cursor.fetchall()}

    for column_name, column_def in _NEW_COLUMNS:
        if column_name not in existing:
            cursor.execute(
                f"ALTER TABLE workspaces ADD COLUMN {column_name} {column_def}"
            )


step(apply_step)
