#!/usr/bin/env python3
"""Run the bounded Codex phase-1 workflow from a workspace root."""
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    workspace_dir = Path.cwd()
    prompt_path = workspace_dir / ".codex" / "prompts" / "phase1.md"
    if not prompt_path.exists():
        print(f"Missing Codex phase-1 prompt: {prompt_path}", file=sys.stderr)
        return 1

    codex_bin = shutil.which("codex")
    if not codex_bin:
        print("codex binary not found in PATH", file=sys.stderr)
        return 1

    prompt = prompt_path.read_text(encoding="utf-8")
    command = [
        codex_bin,
        "exec",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "--search",
        "--color",
        "always",
        "-C",
        str(workspace_dir),
        "-",
    ]

    print(f"Starting Codex phase 1 in {workspace_dir}")
    print(f"Using prompt: {prompt_path}")
    print("Codex will stop automatically after preparation reaches phase 1.4.")
    sys.stdout.flush()

    result = subprocess.run(
        command,
        cwd=str(workspace_dir),
        input=prompt,
        text=True,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
