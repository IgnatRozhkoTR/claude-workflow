"""
Initial database schema -- all 16 tables.

Every statement uses IF NOT EXISTS so the migration is safe to run
against databases that already carry the full schema.
"""
from yoyo import step

step("""
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        path TEXT UNIQUE NOT NULL,
        registered TEXT NOT NULL
    )
""")

step("""
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
    )
""")

step("""
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
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS phase_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        from_phase TEXT NOT NULL,
        to_phase TEXT NOT NULL,
        time TEXT NOT NULL,
        commit_hash TEXT
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS progress_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        phase TEXT NOT NULL,
        summary TEXT NOT NULL,
        details_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS session_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        session_id TEXT NOT NULL,
        started_at TEXT NOT NULL
    )
""")

step("""
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
    )
""")

step("""
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
    )
""")

step("""
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
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS improvements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        context TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        resolved_note TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS verification_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        language TEXT NOT NULL,
        description TEXT,
        origin TEXT NOT NULL DEFAULT 'system',
        created_at TEXT NOT NULL
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS verification_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL REFERENCES verification_profiles(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT,
        command TEXT NOT NULL,
        install_check_command TEXT,
        install_command TEXT,
        enabled BOOLEAN NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 0,
        timeout INTEGER NOT NULL DEFAULT 120,
        fail_severity TEXT NOT NULL DEFAULT 'blocking',
        created_at TEXT NOT NULL
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS project_verification_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        profile_id INTEGER NOT NULL REFERENCES verification_profiles(id) ON DELETE CASCADE,
        subpath TEXT NOT NULL DEFAULT '.',
        UNIQUE(project_id, profile_id, subpath)
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS verification_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        phase TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        started_at TEXT NOT NULL,
        completed_at TEXT
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS verification_step_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES verification_runs(id) ON DELETE CASCADE,
        step_name TEXT NOT NULL,
        profile_name TEXT NOT NULL,
        status TEXT NOT NULL,
        output TEXT,
        duration_ms INTEGER
    )
""")

step("""
    CREATE TABLE IF NOT EXISTS modules_enabled (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        module_id TEXT NOT NULL UNIQUE,
        enabled_at TEXT DEFAULT (datetime('now'))
    )
""")
