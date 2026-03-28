"""
Idempotent corrections to verification profile seed data:
- Rename Checkstyle/Ruff/ESLint steps to Format with updated commands.
- Update SonarScanner commands.
- Ensure SonarScanner exists on every Java profile.
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()

    # Rename Checkstyle -> Format (Java)
    cursor.execute("""
        UPDATE verification_steps SET name = 'Format',
            description = 'Auto-format Java code with google-java-format',
            command = '{ git diff --name-only --diff-filter=ACMR HEAD~1 -- ''*.java''; git ls-files --others --exclude-standard -- ''*.java''; } | sort -u | xargs -r java -jar ~/.claude/tools/google-java-format.jar --replace',
            install_check_command = 'test -f ~/.claude/tools/google-java-format.jar',
            install_command = 'mkdir -p ~/.claude/tools && curl -sL -o ~/.claude/tools/google-java-format.jar https://github.com/google/google-java-format/releases/download/v1.25.2/google-java-format-1.25.2-all-deps.jar',
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

    # Update SonarScanner commands with auto-derived values
    cursor.execute("""
        UPDATE verification_steps SET
            command = 'sonar-scanner -Dsonar.projectKey=$(basename $(pwd)) -Dsonar.organization=${SONAR_ORG:-default} -Dsonar.token=${SONAR_TOKEN} -Dsonar.sources=.',
            install_check_command = 'which sonar-scanner && test -n "$SONAR_TOKEN"'
        WHERE name = 'SonarScanner' AND command = 'sonar-scanner'
    """)

    # Ensure SonarScanner exists on every Java system profile
    from datetime import datetime
    now = datetime.now().isoformat()

    cursor.execute(
        "SELECT id FROM verification_profiles WHERE language = 'java' AND origin = 'system'"
    )
    java_profiles = cursor.fetchall()
    for jp in java_profiles:
        profile_id = jp[0]
        cursor.execute(
            "SELECT id FROM verification_steps WHERE profile_id = ? AND name = 'SonarScanner'",
            (profile_id,),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO verification_steps (profile_id, name, description, command, install_check_command, "
                "install_command, enabled, sort_order, timeout, fail_severity, created_at) "
                'VALUES (?, \'SonarScanner\', \'Run SonarQube analysis\', \'sonar-scanner -Dsonar.projectKey=$(basename $(pwd)) -Dsonar.organization=${SONAR_ORG:-default} -Dsonar.token=${SONAR_TOKEN} -Dsonar.sources=.\', \'which sonar-scanner && test -n "$SONAR_TOKEN"\', '
                "'brew install sonar-scanner', 0, 2, 300, 'warning', ?)",
                (profile_id, now),
            )


step(apply_step)
