"""
Migrate legacy comments + discussions tables into the unified discussions table.

Detection: if the old ``comments`` table exists AND the current discussions
table lacks ``parent_id``, we create a new unified table, copy data, and
swap in.  Otherwise this is a no-op.
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    if "comments" not in tables:
        return

    cursor.execute("PRAGMA table_info(discussions)")
    discussions_columns = {row[1] for row in cursor.fetchall()}
    if "parent_id" in discussions_columns:
        return

    cursor.execute("""
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
        cursor.execute(
            "INSERT INTO discussions_new (workspace_id, text, author, scope, target, status, created_at, resolved_at) "
            "SELECT workspace_id, topic, author, NULL, NULL, status, created_at, resolved_at FROM discussions"
        )

    cursor.execute(
        "INSERT INTO discussions_new (workspace_id, text, author, scope, target, file_path, line_start, line_end, line_hash, status, created_at, resolved_at) "
        "SELECT workspace_id, text, 'user', scope, target, file_path, line_start, line_end, line_hash, "
        "CASE WHEN resolved = 1 THEN 'resolved' ELSE 'open' END, created_at, resolved_at FROM comments"
    )

    cursor.execute("DROP TABLE comments")
    if "discussions" in tables:
        cursor.execute("DROP TABLE discussions")
    cursor.execute("ALTER TABLE discussions_new RENAME TO discussions")


step(apply_step)
