"""
Idempotent corrections to verification profile seed data:
- Rename Checkstyle/Ruff/ESLint steps to Format with updated commands.

The Format step for Java uses ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar
(an env-var-interpolated shell path exported by app.py at startup). This keeps the
DB portable across installs.  0017_repoint_format_tools.py is the companion
migration that rewrites any legacy ~/.claude/tools rows written before this change.
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()

    # Rename Checkstyle -> Format (Java).
    # Commands use ${GOVERNED_WORKFLOW_TOOLS_DIR} (exported by app.py at startup)
    # so the DB remains portable. 0017_repoint_format_tools.py rewrites rows that
    # still contain the old ~/.claude/tools literal.
    cursor.execute("""
        UPDATE verification_steps SET name = 'Format',
            description = 'Auto-format Java code with google-java-format',
            command = '{ git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.java''; git ls-files --others --exclude-standard -- ''*.java''; } | sort -u | xargs -r java -jar ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar --replace',
            install_check_command = 'test -f ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar',
            install_command = 'mkdir -p ${GOVERNED_WORKFLOW_TOOLS_DIR} && curl -sL -o ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar https://github.com/google/google-java-format/releases/download/v1.25.2/google-java-format-1.25.2-all-deps.jar',
            fail_severity = 'blocking'
        WHERE name = 'Checkstyle'
    """)

    # Rename Ruff -> Format (Python)
    cursor.execute("""
        UPDATE verification_steps SET name = 'Format',
            description = 'Auto-format Python code with Ruff',
            command = '{ git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.py''; git ls-files --others --exclude-standard -- ''*.py''; } | sort -u | xargs -r ruff format && { git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.py''; git ls-files --others --exclude-standard -- ''*.py''; } | sort -u | xargs -r ruff check --fix',
            install_check_command = 'which ruff',
            install_command = 'pip install ruff',
            fail_severity = 'blocking'
        WHERE name = 'Ruff'
    """)

    # Rename ESLint -> Format (TypeScript)
    cursor.execute("""
        UPDATE verification_steps SET name = 'Format',
            description = 'Auto-format with ESLint and Prettier',
            command = '{ git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.ts'' ''*.tsx'' ''*.js'' ''*.jsx''; git ls-files --others --exclude-standard -- ''*.ts'' ''*.tsx'' ''*.js'' ''*.jsx''; } | sort -u | xargs -r npx eslint --fix && { git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.ts'' ''*.tsx'' ''*.js'' ''*.jsx''; git ls-files --others --exclude-standard -- ''*.ts'' ''*.tsx'' ''*.js'' ''*.jsx''; } | sort -u | xargs -r npx prettier --write',
            install_check_command = 'test -f node_modules/.bin/eslint',
            install_command = 'npm install eslint prettier',
            fail_severity = 'blocking'
        WHERE name = 'ESLint'
    """)


step(apply_step)
