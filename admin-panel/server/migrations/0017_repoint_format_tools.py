"""
Repoint google-java-format paths from the legacy ~/.claude/tools literal to the
portable ${GOVERNED_WORKFLOW_TOOLS_DIR} env-var form.

Fresh DBs: this migration is a no-op because 0002 and 0011 already write the
correct env-var form.

Existing DBs: any verification_steps rows whose command,
install_check_command, or install_command still contain
'~/.claude/tools/google-java-format.jar' are updated in-place. The
substitution is idempotent — running this migration twice leaves rows
unchanged after the first run.

GOVERNED_WORKFLOW_TOOLS_DIR is exported by app.py at startup (pointing to
<repo>/claude/tools/) so the verification runner picks it up automatically in
every subprocess it spawns.
"""
from yoyo import step

_LEGACY = "~/.claude/tools/google-java-format.jar"
_NEW = "${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar"

_LEGACY_INSTALL_PREFIX = "mkdir -p ~/.claude/tools && curl -sL -o ~/.claude/tools/google-java-format.jar"
_NEW_INSTALL_PREFIX = "mkdir -p ${GOVERNED_WORKFLOW_TOOLS_DIR} && curl -sL -o ${GOVERNED_WORKFLOW_TOOLS_DIR}/google-java-format.jar"


def apply_step(conn):
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, command, install_check_command, install_command "
        "FROM verification_steps "
        "WHERE command LIKE ? "
        "   OR install_check_command LIKE ? "
        "   OR install_command LIKE ?",
        (f"%{_LEGACY}%", f"%{_LEGACY}%", f"%{_LEGACY}%"),
    )
    rows = cursor.fetchall()

    for row in rows:
        row_id, command, install_check, install_cmd = row

        new_command = command.replace(_LEGACY, _NEW) if command else command
        new_install_check = (
            install_check.replace(_LEGACY, _NEW) if install_check else install_check
        )
        new_install_cmd = (
            install_cmd.replace(_LEGACY_INSTALL_PREFIX, _NEW_INSTALL_PREFIX)
            if install_cmd
            else install_cmd
        )
        # Catch any remaining legacy jar reference in install_command
        if new_install_cmd:
            new_install_cmd = new_install_cmd.replace(_LEGACY, _NEW)

        cursor.execute(
            "UPDATE verification_steps "
            "SET command = ?, install_check_command = ?, install_command = ? "
            "WHERE id = ?",
            (new_command, new_install_check, new_install_cmd, row_id),
        )


step(apply_step)
