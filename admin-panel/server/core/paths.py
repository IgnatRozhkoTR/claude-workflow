"""Central path resolution for governed-workflow.

All asset paths are resolved relative to the repository root, never to
~/.claude or any other fixed home-directory location.  This makes the
governed-workflow repo relocatable: install it anywhere and set
GOVERNED_WORKFLOW_REPO to the install path if the parents[] computation
does not match your layout.

Depth from this file to REPO_ROOT:
  admin-panel/server/core/paths.py
  parents[0] = core/
  parents[1] = server/
  parents[2] = admin-panel/
  parents[3] = REPO_ROOT  (contains admin-panel/, hooks/, agents/, …)
"""
import os
from pathlib import Path

_repo_env = os.environ.get("GOVERNED_WORKFLOW_REPO", "")
REPO_ROOT: Path = (
    Path(_repo_env).resolve()
    if _repo_env
    else Path(__file__).resolve().parents[3]
)

DEFAULT_HOOKS_DIR = REPO_ROOT / "hooks"
DEFAULT_AGENTS_DIR = REPO_ROOT / "agents"
DEFAULT_RULES_DIR = REPO_ROOT / "rules"
DEFAULT_DEFAULTS_DIR = REPO_ROOT / "defaults"
DEFAULT_CODEX_DIR = REPO_ROOT / ".codex"
DEFAULT_TOOLS_DIR = REPO_ROOT / "tools"
DEFAULT_MODULES_DIR = REPO_ROOT / "modules"
DEFAULT_SKILLS_DIR = REPO_ROOT / "skills"

DEFAULT_FUNNEL_TEMPLATE = DEFAULT_DEFAULTS_DIR / ".mcp-funnel.json"
DEFAULT_MCP_TEMPLATE = REPO_ROOT / ".mcp.json"
DEFAULT_GIT_RULES = DEFAULT_DEFAULTS_DIR / "git-rules.md"
DEFAULT_GIT_HOOKS_DIR = DEFAULT_DEFAULTS_DIR / "git-hooks"

STATE_DIR: Path = Path(
    os.environ.get("GOVERNED_WORKFLOW_STATE_DIR") or REPO_ROOT / ".local" / "state"
)

TELEGRAM_STATE_DIR: Path = Path(
    os.environ.get("GOVERNED_WORKFLOW_TELEGRAM_STATE")
    or REPO_ROOT / ".local" / "channels" / "telegram"
)


def hook_command(name: str, interpreter: str = "python3") -> str:
    """Return the shell command string for invoking a hook by filename.

    Args:
        name: Hook filename, e.g. ``session-start.py`` or ``user-prompt-submit.sh``.
        interpreter: Shell interpreter prefix, e.g. ``python3`` or ``bash``.

    Returns:
        A string like ``python3 /abs/path/to/repo/hooks/session-start.py``.
        Contains no ``~/.claude`` literals.
    """
    return f"{interpreter} {DEFAULT_HOOKS_DIR / name}"
