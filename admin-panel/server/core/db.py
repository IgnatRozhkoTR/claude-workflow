"""Database connection and schema."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "admin-panel.db"


def ws_field(ws, field, default=None):
    """Get a workspace field with a default for columns added via migration."""
    return ws[field] if field in ws.keys() else default


def get_db():
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA busy_timeout = 5000")
    return db


@contextmanager
def get_db_ctx():
    """Context manager for DB connections: ``with get_db_ctx() as db:``."""
    db = get_db()
    try:
        yield db
    finally:
        db.close()


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
            );

            CREATE TABLE IF NOT EXISTS verification_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                language TEXT NOT NULL,
                description TEXT,
                origin TEXT NOT NULL DEFAULT 'system',
                created_at TEXT NOT NULL
            );

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
            );

            CREATE TABLE IF NOT EXISTS project_verification_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                profile_id INTEGER NOT NULL REFERENCES verification_profiles(id) ON DELETE CASCADE,
                subpath TEXT NOT NULL DEFAULT '.',
                UNIQUE(project_id, profile_id, subpath)
            );

            CREATE TABLE IF NOT EXISTS verification_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                phase TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS verification_step_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES verification_runs(id) ON DELETE CASCADE,
                step_name TEXT NOT NULL,
                profile_name TEXT NOT NULL,
                status TEXT NOT NULL,
                output TEXT,
                duration_ms INTEGER
            );

            CREATE TABLE IF NOT EXISTS modules_enabled (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_id TEXT NOT NULL UNIQUE,
                enabled_at TEXT DEFAULT (datetime('now'))
            );
        """)
        _migrate_db(db)
        _seed_verification_profiles(db)
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


def _seed_verification_profiles(db):
    """Seed default verification profiles on first run and apply migrations."""
    from datetime import datetime
    now = datetime.now().isoformat()

    existing = db.execute("SELECT COUNT(*) as cnt FROM verification_profiles WHERE origin = 'system'").fetchone()["cnt"]
    if existing == 0:
        profiles = [
            ("Java (Gradle)", "java", "Java project using Gradle build system", [
                ("Compilation", "Compile Java sources and test sources", "./gradlew compileJava compileTestJava -q", "test -f ./gradlew", None, True, 0, 180, "blocking"),
                ("Format", "Auto-format Java code with google-java-format", "{ git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.java'; git ls-files --others --exclude-standard -- '*.java'; } | sort -u | xargs -r java -jar ~/.claude/tools/google-java-format.jar --replace", "test -f ~/.claude/tools/google-java-format.jar", "mkdir -p ~/.claude/tools && curl -sL -o ~/.claude/tools/google-java-format.jar https://github.com/google/google-java-format/releases/download/v1.25.2/google-java-format-1.25.2-all-deps.jar", False, 1, 120, "blocking"),
                ("SonarScanner", "Run SonarQube analysis", "sonar-scanner -Dsonar.projectKey=$(basename $(pwd)) -Dsonar.organization=${SONAR_ORG:-default} -Dsonar.token=${SONAR_TOKEN} -Dsonar.sources=.", "which sonar-scanner && test -n \"$SONAR_TOKEN\"", "brew install sonar-scanner", False, 2, 300, "warning"),
            ]),
            ("Java (Maven)", "java", "Java project using Maven build system", [
                ("Compilation", "Compile Java sources and test sources", "mvn compile test-compile -q", "test -f pom.xml && which mvn", None, True, 0, 180, "blocking"),
                ("Format", "Auto-format Java code with google-java-format", "{ git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.java'; git ls-files --others --exclude-standard -- '*.java'; } | sort -u | xargs -r java -jar ~/.claude/tools/google-java-format.jar --replace", "test -f ~/.claude/tools/google-java-format.jar", "mkdir -p ~/.claude/tools && curl -sL -o ~/.claude/tools/google-java-format.jar https://github.com/google/google-java-format/releases/download/v1.25.2/google-java-format-1.25.2-all-deps.jar", False, 1, 120, "blocking"),
                ("SonarScanner", "Run SonarQube analysis", "sonar-scanner -Dsonar.projectKey=$(basename $(pwd)) -Dsonar.organization=${SONAR_ORG:-default} -Dsonar.token=${SONAR_TOKEN} -Dsonar.sources=.", "which sonar-scanner && test -n \"$SONAR_TOKEN\"", "brew install sonar-scanner", False, 2, 300, "warning"),
            ]),
            ("Python", "python", "Python project", [
                ("Syntax Check", "Compile all Python files to check for syntax errors", "python3 -m compileall -q .", "which python3", None, True, 0, 60, "blocking"),
                ("Format", "Auto-format Python code with Ruff", "{ git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.py'; git ls-files --others --exclude-standard -- '*.py'; } | sort -u | xargs -r ruff format && { git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.py'; git ls-files --others --exclude-standard -- '*.py'; } | sort -u | xargs -r ruff check --fix", "which ruff", "pip install ruff", False, 1, 60, "blocking"),
                ("Mypy", "Static type checking with Mypy", "mypy .", "which mypy", "pip install mypy", False, 2, 120, "warning"),
            ]),
            ("TypeScript", "typescript", "TypeScript project", [
                ("Compilation", "Type-check TypeScript sources", "npx tsc --noEmit", "test -f tsconfig.json", None, True, 0, 120, "blocking"),
                ("Format", "Auto-format with ESLint and Prettier", "{ git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.ts' '*.tsx' '*.js' '*.jsx'; git ls-files --others --exclude-standard -- '*.ts' '*.tsx' '*.js' '*.jsx'; } | sort -u | xargs -r npx eslint --fix && { git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.ts' '*.tsx' '*.js' '*.jsx'; git ls-files --others --exclude-standard -- '*.ts' '*.tsx' '*.js' '*.jsx'; } | sort -u | xargs -r npx prettier --write", "test -f node_modules/.bin/eslint", "npm install eslint prettier", False, 1, 120, "blocking"),
            ]),
        ]

        for name, language, description, steps in profiles:
            cursor = db.execute(
                "INSERT INTO verification_profiles (name, language, description, origin, created_at) VALUES (?, ?, ?, 'system', ?)",
                (name, language, description, now)
            )
            profile_id = cursor.lastrowid
            for step_name, step_desc, command, install_check, install_cmd, enabled, sort_order, timeout, severity in steps:
                db.execute(
                    "INSERT INTO verification_steps (profile_id, name, description, command, install_check_command, install_command, enabled, sort_order, timeout, fail_severity, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (profile_id, step_name, step_desc, command, install_check, install_cmd, 1 if enabled else 0, sort_order, timeout, severity, now)
                )

    # Migrations: always run (idempotent)
    # Migrate: rename Checkstyle/ESLint/Ruff steps to Format with auto-fix commands
    db.execute("""
        UPDATE verification_steps SET name = 'Format',
            description = 'Auto-format Java code with google-java-format',
            command = '{ git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.java''; git ls-files --others --exclude-standard -- ''*.java''; } | sort -u | xargs -r java -jar ~/.claude/tools/google-java-format.jar --replace',
            install_check_command = 'test -f ~/.claude/tools/google-java-format.jar',
            install_command = 'mkdir -p ~/.claude/tools && curl -sL -o ~/.claude/tools/google-java-format.jar https://github.com/google/google-java-format/releases/download/v1.25.2/google-java-format-1.25.2-all-deps.jar',
            fail_severity = 'blocking'
        WHERE name = 'Checkstyle'
    """)
    db.execute("""
        UPDATE verification_steps SET name = 'Format',
            description = 'Auto-format Python code with Ruff',
            command = '{ git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.py''; git ls-files --others --exclude-standard -- ''*.py''; } | sort -u | xargs -r ruff format && { git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.py''; git ls-files --others --exclude-standard -- ''*.py''; } | sort -u | xargs -r ruff check --fix',
            install_check_command = 'which ruff',
            install_command = 'pip install ruff',
            fail_severity = 'blocking'
        WHERE name = 'Ruff'
    """)
    db.execute("""
        UPDATE verification_steps SET name = 'Format',
            description = 'Auto-format with ESLint and Prettier',
            command = '{ git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.ts'' ''*.tsx'' ''*.js'' ''*.jsx''; git ls-files --others --exclude-standard -- ''*.ts'' ''*.tsx'' ''*.js'' ''*.jsx''; } | sort -u | xargs -r npx eslint --fix && { git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.ts'' ''*.tsx'' ''*.js'' ''*.jsx''; git ls-files --others --exclude-standard -- ''*.ts'' ''*.tsx'' ''*.js'' ''*.jsx''; } | sort -u | xargs -r npx prettier --write',
            install_check_command = 'test -f node_modules/.bin/eslint',
            install_command = 'npm install eslint prettier',
            fail_severity = 'blocking'
        WHERE name = 'ESLint'
    """)

    # Update SonarScanner commands with auto-derived values
    db.execute("""
        UPDATE verification_steps SET
            command = 'sonar-scanner -Dsonar.projectKey=$(basename $(pwd)) -Dsonar.organization=${SONAR_ORG:-default} -Dsonar.token=${SONAR_TOKEN} -Dsonar.sources=.',
            install_check_command = 'which sonar-scanner && test -n "$SONAR_TOKEN"'
        WHERE name = 'SonarScanner' AND command = 'sonar-scanner'
    """)

    # Add SonarScanner to Java profiles if missing
    java_profiles = db.execute(
        "SELECT id FROM verification_profiles WHERE language = 'java' AND origin = 'system'"
    ).fetchall()
    for jp in java_profiles:
        has_sonar = db.execute(
            "SELECT id FROM verification_steps WHERE profile_id = ? AND name = 'SonarScanner'",
            (jp["id"],)
        ).fetchone()
        if not has_sonar:
            db.execute(
                "INSERT INTO verification_steps (profile_id, name, description, command, install_check_command, "
                "install_command, enabled, sort_order, timeout, fail_severity, created_at) "
                "VALUES (?, 'SonarScanner', 'Run SonarQube analysis', 'sonar-scanner -Dsonar.projectKey=$(basename $(pwd)) -Dsonar.organization=${SONAR_ORG:-default} -Dsonar.token=${SONAR_TOKEN} -Dsonar.sources=.', 'which sonar-scanner && test -n \"$SONAR_TOKEN\"', "
                "'brew install sonar-scanner', 0, 2, 300, 'warning', ?)",
                (jp["id"], now)
            )


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

    # Migrate workspace_verification_profiles → project_verification_profiles
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "workspace_verification_profiles" in tables and "project_verification_profiles" not in tables:
        db.execute("""
            CREATE TABLE project_verification_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                profile_id INTEGER NOT NULL REFERENCES verification_profiles(id) ON DELETE CASCADE,
                subpath TEXT NOT NULL DEFAULT '.',
                UNIQUE(project_id, profile_id, subpath)
            )
        """)
        db.execute("""
            INSERT OR IGNORE INTO project_verification_profiles (project_id, profile_id, subpath)
            SELECT w.project_id, wvp.profile_id, wvp.subpath
            FROM workspace_verification_profiles wvp
            JOIN workspaces w ON wvp.workspace_id = w.id
        """)
        db.execute("DROP TABLE workspace_verification_profiles")
