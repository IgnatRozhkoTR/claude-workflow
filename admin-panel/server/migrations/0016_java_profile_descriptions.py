"""Update Java system profiles with agent setup instructions for JDK 17 discovery."""
from yoyo import step


def apply_step(conn):
    cursor = conn.cursor()

    description = (
        "Java build verification. "
        "LSP setup requires JDK 17: discover it using `/usr/libexec/java_home -v 17` (macOS) "
        "or `find /usr/lib/jvm -maxdepth 1 -name '*17*' -type d 2>/dev/null | head -1` (Linux). "
        "If not found, install it: macOS: `brew install --cask zulu@17`, "
        "Linux: `sudo apt-get install -y openjdk-17-jdk` (or equivalent for distro). "
        "Once the JDK 17 path is known, call `workspace_update_verification_profile` with: "
        "lsp_command='bash', lsp_args='[\"-c\", \"JAVA_HOME=<resolved_path> exec jdtls --jvm-arg=-Xmx1G\"]' "
        "(replace <resolved_path> with the actual path found)."
    )

    cursor.execute(
        "UPDATE verification_profiles SET description = ? WHERE name = 'Java (Gradle)' AND origin = 'system'",
        (description,)
    )
    cursor.execute(
        "UPDATE verification_profiles SET description = ? WHERE name = 'Java (Maven)' AND origin = 'system'",
        (description,)
    )


step(apply_step)
