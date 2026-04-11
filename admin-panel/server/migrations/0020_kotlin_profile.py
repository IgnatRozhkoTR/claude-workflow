"""
Seed the Kotlin (Gradle) verification profile.

Adds a system-origin profile so any fresh device gets a working Kotlin setup
without manual configuration. The profile uses:

- Compilation: ./gradlew compileKotlin compileTestKotlin
- Format: ktlint (downloaded into ${GOVERNED_WORKFLOW_TOOLS_DIR}, same pattern as
  google-java-format on the Java profiles, so it's portable across macOS and Linux
  without requiring brew on the build path)
- LSP: the official JetBrains kotlin-lsp (pre-alpha but Gradle JVM-only projects
  are supported out-of-the-box). It ships with its own bundled JRE, so it does
  not depend on JAVA_HOME or any system Java version.

Idempotent: skips creation if a system-origin Kotlin (Gradle) profile already
exists. Safe to re-run.
"""
from datetime import datetime

from yoyo import step


KTLINT_VERSION = "1.8.0"
KTLINT_BIN = "${GOVERNED_WORKFLOW_TOOLS_DIR}/ktlint"
KTLINT_FORMAT_COMMAND = (
    "{ git diff --name-only --diff-filter=ACMR HEAD~1 -- '*.kt'; "
    "git ls-files --others --exclude-standard -- '*.kt'; } | sort -u | "
    "xargs -r " + KTLINT_BIN + " --format"
)
KTLINT_INSTALL_CHECK = "test -x " + KTLINT_BIN
KTLINT_INSTALL_COMMAND = (
    "mkdir -p ${GOVERNED_WORKFLOW_TOOLS_DIR} && "
    "curl -sL -o " + KTLINT_BIN + " "
    "https://github.com/pinterest/ktlint/releases/download/" + KTLINT_VERSION + "/ktlint && "
    "chmod +x " + KTLINT_BIN
)

DESCRIPTION = (
    "Kotlin build verification using Gradle. "
    "LSP setup uses the official JetBrains kotlin-lsp (pre-alpha but Gradle JVM-only "
    "projects are supported out-of-the-box). It ships with its own bundled JRE so no "
    "JAVA_HOME juggling is required. "
    "Install: macOS: `brew install --cask kotlin-lsp`. "
    "Linux: download the latest archive from https://github.com/Kotlin/kotlin-lsp/releases, "
    "extract it, and symlink `kotlin-lsp.sh` to a directory on PATH as `kotlin-lsp`. "
    "Smoke test: `kotlin-lsp --help`. "
    "Notes: kotlin-lsp does its full Gradle import + indexing on the first `initialize` "
    "request — give it 30-90 seconds before querying references on a fresh project. "
    "Subsequent starts reuse the cache and are much faster. "
    "Limitations (per upstream): Kotlin Multiplatform and Maven are not yet supported; "
    "stick to JVM Gradle projects for now."
)


def apply_step(conn):
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM verification_profiles "
        "WHERE name = 'Kotlin (Gradle)' AND origin = 'system'"
    )
    if cursor.fetchone() is not None:
        return

    now = datetime.now().isoformat()

    cursor.execute(
        "INSERT INTO verification_profiles "
        "(name, language, description, origin, lsp_command, lsp_args, "
        " lsp_install_check_command, lsp_install_command, created_at) "
        "VALUES (?, ?, ?, 'system', ?, ?, ?, ?, ?)",
        (
            "Kotlin (Gradle)",
            "kotlin",
            DESCRIPTION,
            "kotlin-lsp",
            '["--stdio"]',
            "which kotlin-lsp",
            "brew install --cask kotlin-lsp",
            now,
        ),
    )
    profile_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO verification_steps "
        "(profile_id, name, description, command, install_check_command, "
        " install_command, enabled, sort_order, timeout, fail_severity, created_at) "
        "VALUES (?, 'Compilation', 'Compile Kotlin sources and test sources', "
        "'./gradlew compileKotlin compileTestKotlin -q', 'test -f ./gradlew', "
        "NULL, 1, 0, 240, 'blocking', ?)",
        (profile_id, now),
    )

    cursor.execute(
        "INSERT INTO verification_steps "
        "(profile_id, name, description, command, install_check_command, "
        " install_command, enabled, sort_order, timeout, fail_severity, created_at) "
        "VALUES (?, 'Format', 'Auto-format Kotlin code with ktlint', "
        "?, ?, ?, 1, 1, 180, 'blocking', ?)",
        (profile_id, KTLINT_FORMAT_COMMAND, KTLINT_INSTALL_CHECK, KTLINT_INSTALL_COMMAND, now),
    )


step(apply_step)
