"""Database connection and schema."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "admin-panel.db"


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    db = get_db()
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT UNIQUE NOT NULL,
                registered TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                branch TEXT NOT NULL,
                sanitized_branch TEXT NOT NULL,
                session_id TEXT,
                working_dir TEXT NOT NULL,
                created TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                phase TEXT NOT NULL DEFAULT '0',
                scope_json TEXT DEFAULT '{}',
                plan_json TEXT DEFAULT '{"description":"","systemDiagram":"","execution":[]}',
                commit_message TEXT,
                gate_nonce TEXT,
                source_branch TEXT,
                locale TEXT NOT NULL DEFAULT 'en',
                UNIQUE(project_id, sanitized_branch)
            );

            CREATE TABLE IF NOT EXISTS discussions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                parent_id INTEGER REFERENCES discussions(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT 'user',
                scope TEXT,
                target TEXT,
                file_path TEXT,
                line_start INTEGER,
                line_end INTEGER,
                line_hash TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                type TEXT DEFAULT 'general',
                hidden INTEGER DEFAULT 0,
                resolution TEXT
            );

            CREATE TABLE IF NOT EXISTS phase_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                from_phase TEXT NOT NULL,
                to_phase TEXT NOT NULL,
                time TEXT NOT NULL,
                commit_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS progress_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                phase TEXT NOT NULL,
                summary TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL,
                started_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                topic TEXT NOT NULL,
                summary TEXT,
                findings_json TEXT NOT NULL,
                proven INTEGER NOT NULL DEFAULT 0,
                proven_notes TEXT,
                created_at TEXT NOT NULL,
                discussion_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS review_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                file_path TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                severity TEXT NOT NULL,
                description TEXT NOT NULL,
                code_snippet TEXT NOT NULL,
                resolution TEXT NOT NULL DEFAULT 'open',
                validated INTEGER NOT NULL DEFAULT 0,
                validation_reason TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS acceptance_criteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                description TEXT NOT NULL,
                details_json TEXT,
                source TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'proposed',
                validated INTEGER NOT NULL DEFAULT 0,
                validation_message TEXT,
                created_at TEXT NOT NULL
            );
        """)
        _migrate_db(db)
        db.commit()
    finally:
        db.close()


def _migrate_unified_discussions(db):
    """Migrate old comments + discussions tables into unified discussions table."""
    tables = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}

    if "comments" not in tables:
        return

    discussions_columns = {row[1] for row in db.execute("PRAGMA table_info(discussions)")}
    if "parent_id" in discussions_columns:
        return

    db.execute("""
        CREATE TABLE discussions_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            parent_id INTEGER REFERENCES discussions_new(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT 'user',
            scope TEXT,
            target TEXT,
            file_path TEXT,
            line_start INTEGER,
            line_end INTEGER,
            line_hash TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            type TEXT DEFAULT 'general',
            hidden INTEGER DEFAULT 0
        )
    """)

    if "discussions" in tables:
        db.execute(
            "INSERT INTO discussions_new (workspace_id, text, author, scope, target, status, created_at, resolved_at) "
            "SELECT workspace_id, topic, author, NULL, NULL, status, created_at, resolved_at FROM discussions"
        )

    db.execute(
        "INSERT INTO discussions_new (workspace_id, text, author, scope, target, file_path, line_start, line_end, line_hash, status, created_at, resolved_at) "
        "SELECT workspace_id, text, 'user', scope, target, file_path, line_start, line_end, line_hash, "
        "CASE WHEN resolved = 1 THEN 'resolved' ELSE 'open' END, created_at, resolved_at FROM comments"
    )

    db.execute("DROP TABLE comments")
    if "discussions" in tables:
        db.execute("DROP TABLE discussions")
    db.execute("ALTER TABLE discussions_new RENAME TO discussions")


def _migrate_db(db):
    existing_columns = {row[1] for row in db.execute("PRAGMA table_info(workspaces)")}

    new_columns = [
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
    for column_name, column_def in new_columns:
        if column_name not in existing_columns:
            db.execute(f"ALTER TABLE workspaces ADD COLUMN {column_name} {column_def}")

    _migrate_unified_discussions(db)

    phase_history_columns = {row[1]: row[2] for row in db.execute("PRAGMA table_info(phase_history)")}
    if phase_history_columns.get("from_phase", "").upper() == "INTEGER":
        db.execute("DROP TABLE phase_history")
        db.execute("""
            CREATE TABLE phase_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                from_phase TEXT NOT NULL,
                to_phase TEXT NOT NULL,
                time TEXT NOT NULL
            )
        """)

    ph_columns = {row[1] for row in db.execute("PRAGMA table_info(phase_history)")}
    if "commit_hash" not in ph_columns:
        db.execute("ALTER TABLE phase_history ADD COLUMN commit_hash TEXT")

    # Research discussions: add type and hidden to discussions table
    disc_columns = {row[1] for row in db.execute("PRAGMA table_info(discussions)")}
    if "type" not in disc_columns:
        db.execute("ALTER TABLE discussions ADD COLUMN type TEXT DEFAULT 'general'")
    if "hidden" not in disc_columns:
        db.execute("ALTER TABLE discussions ADD COLUMN hidden INTEGER DEFAULT 0")
    if "resolution" not in disc_columns:
        db.execute("ALTER TABLE discussions ADD COLUMN resolution TEXT")
    db.execute("UPDATE discussions SET resolution = 'open' WHERE scope = 'review' AND resolution IS NULL")

    # Research linking: add discussion_id to research_entries table
    research_columns = {row[1] for row in db.execute("PRAGMA table_info(research_entries)")}
    if "discussion_id" not in research_columns:
        db.execute("ALTER TABLE research_entries ADD COLUMN discussion_id INTEGER")
    if "summary" not in research_columns:
        db.execute("ALTER TABLE research_entries ADD COLUMN summary TEXT")

    # Normalize review comment scopes
    db.execute("UPDATE discussions SET scope = 'review' WHERE scope IN ('diff', 'file')")
