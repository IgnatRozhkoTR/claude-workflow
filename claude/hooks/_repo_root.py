import os
from pathlib import Path


def _resolve_governed_repo_root() -> Path:
    """Return the governed-workflow repo root without importing admin-panel packages.

    Resolution order:
    1. GOVERNED_WORKFLOW_REPO env var (absolute path).
    2. Walk parents of this file looking for a directory that contains both
       admin-panel/ and claude/hooks/.
    3. Fallback: two levels up from this file (claude/hooks/../.. == repo root).
    """
    env_root = os.environ.get("GOVERNED_WORKFLOW_REPO", "")
    if env_root:
        return Path(env_root).resolve()

    this_file = Path(__file__).resolve()
    for parent in this_file.parents:
        if (parent / "admin-panel").is_dir() and (parent / "claude" / "hooks").is_dir():
            return parent

    return this_file.parent.parent


GOVERNED_REPO_ROOT = _resolve_governed_repo_root()
ADMIN_PANEL_DIR = GOVERNED_REPO_ROOT / "admin-panel"
