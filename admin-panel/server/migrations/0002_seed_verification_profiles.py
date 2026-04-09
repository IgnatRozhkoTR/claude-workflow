"""
Seed default verification profiles (system origin) on first run.
"""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM verification_profiles WHERE origin = 'system'"
    )
    if cursor.fetchone()[0] != 0:
        return

    from datetime import datetime
    now = datetime.now().isoformat()

    profiles = [
        ("Java (Gradle)", "java", "Java project using Gradle build system", [
            ("Compilation", "Compile Java sources and test sources", "./gradlew compileJava compileTestJava -q", "test -f ./gradlew", None, True, 0, 180, "blocking"),
            ("Format", "Auto-format Java code with google-java-format", "{ git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.java'; git ls-files --others --exclude-standard -- '*.java'; } | sort -u | xargs -r java -jar ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar --replace", "test -f ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar", "mkdir -p ${GOVERNED_WORKFLOW_TOOLS_DIR} && curl -sL -o ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar https://github.com/google/google-java-format/releases/download/v1.25.2/google-java-format-1.25.2-all-deps.jar", False, 1, 120, "blocking"),
            ("SonarScanner", "Run SonarQube analysis", "sonar-scanner -Dsonar.projectKey=$(basename $(pwd)) -Dsonar.organization=${SONAR_ORG:-default} -Dsonar.token=${SONAR_TOKEN} -Dsonar.sources=.", 'which sonar-scanner && test -n "$SONAR_TOKEN"', "brew install sonar-scanner", False, 2, 300, "warning"),
        ]),
        ("Java (Maven)", "java", "Java project using Maven build system", [
            ("Compilation", "Compile Java sources and test sources", "mvn compile test-compile -q", "test -f pom.xml && which mvn", None, True, 0, 180, "blocking"),
            ("Format", "Auto-format Java code with google-java-format", "{ git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.java'; git ls-files --others --exclude-standard -- '*.java'; } | sort -u | xargs -r java -jar ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar --replace", "test -f ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar", "mkdir -p ${GOVERNED_WORKFLOW_TOOLS_DIR} && curl -sL -o ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar https://github.com/google/google-java-format/releases/download/v1.25.2/google-java-format-1.25.2-all-deps.jar", False, 1, 120, "blocking"),
            ("SonarScanner", "Run SonarQube analysis", "sonar-scanner -Dsonar.projectKey=$(basename $(pwd)) -Dsonar.organization=${SONAR_ORG:-default} -Dsonar.token=${SONAR_TOKEN} -Dsonar.sources=.", 'which sonar-scanner && test -n "$SONAR_TOKEN"', "brew install sonar-scanner", False, 2, 300, "warning"),
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
        cursor.execute(
            "INSERT INTO verification_profiles (name, language, description, origin, created_at) VALUES (?, ?, ?, 'system', ?)",
            (name, language, description, now),
        )
        profile_id = cursor.lastrowid
        for step_name, step_desc, command, install_check, install_cmd, enabled, sort_order, timeout, severity in steps:
            cursor.execute(
                "INSERT INTO verification_steps (profile_id, name, description, command, install_check_command, install_command, enabled, sort_order, timeout, fail_severity, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (profile_id, step_name, step_desc, command, install_check, install_cmd, 1 if enabled else 0, sort_order, timeout, severity, now),
            )


step(apply_step)
