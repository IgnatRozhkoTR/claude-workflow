#!/usr/bin/env python3
"""Run the bounded Codex review workflow from a workspace root."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from core.codex import mark_codex_review_completed, mark_codex_review_failed  # noqa: E402
from core.db import get_db_ctx  # noqa: E402
from core.terminal import notify_workspace  # noqa: E402


def _load_workspace(workspace_id):
    with get_db_ctx() as db:
        return db.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()


def _notify(workspace_id, message):
    ws = _load_workspace(workspace_id)
    if ws:
        notify_workspace(ws, message)


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", type=int, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--branch", required=True)
    return parser.parse_args()


def main():
    args = _parse_args()
    workspace_dir = Path.cwd()
    prompt_path = Path.home() / ".claude" / ".codex" / "prompts" / "review.md"
    if not prompt_path.exists():
        error = f"Missing Codex review prompt: {prompt_path}"
        print(error, file=sys.stderr)
        mark_codex_review_failed(args.workspace_id, error)
        _notify(args.workspace_id, "Codex review failed because the review prompt is missing.")
        return 1

    codex_bin = shutil.which("codex")
    if not codex_bin:
        error = "codex binary not found in PATH"
        print(error, file=sys.stderr)
        mark_codex_review_failed(args.workspace_id, error)
        _notify(args.workspace_id, "Codex review failed because the codex binary is not available.")
        return 1

    prompt = prompt_path.read_text(encoding="utf-8")
    command = [
        codex_bin,
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--color",
        "always",
        "-C",
        str(workspace_dir),
        "-",
    ]

    print(f"Starting Codex review in {workspace_dir}")
    print(f"Using prompt: {prompt_path}")
    print("Codex review will stop automatically after phase 4.0 review is complete.")
    sys.stdout.flush()

    result = subprocess.run(
        command,
        cwd=str(workspace_dir),
        input=prompt,
        text=True,
    )

    if result.returncode == 0:
        mark_codex_review_completed(args.workspace_id)
        _notify(
            args.workspace_id,
            "Codex review completed and submitted any findings it found. You may proceed once the rest of phase 4.0 is done.",
        )
        return 0

    error = f"Codex review exited with status {result.returncode}"
    mark_codex_review_failed(args.workspace_id, error)
    _notify(
        args.workspace_id,
        "Codex review failed. Check the Codex review session before advancing out of phase 4.0.",
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
