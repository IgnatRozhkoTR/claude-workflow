"""Unit tests for terminal helper functions."""
import sys
from pathlib import Path

SERVER_DIR = str(Path(__file__).resolve().parent.parent)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from terminal import _strip_ansi, _is_claude_ready


REALISTIC_PANE = """claude --dangerously-skip-permissions
 ▐▛███▜▌   Claude Code v2.1.85
▝▜█████▛▘  Opus 4.6 (1M context)
  ▘▘ ▝▝    /Users/test

────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────
"""

TRUST_PROMPT_PANE = """Do you trust the files in /Users/test/project?
Press Enter to confirm.
"""


def test_strip_ansi_plain_text():
    assert _strip_ansi("hello world") == "hello world"


def test_strip_ansi_removes_color_codes():
    colored = "\x1b[31mred text\x1b[0m"
    assert _strip_ansi(colored) == "red text"


def test_strip_ansi_removes_cursor_codes():
    with_cursor = "\x1b[2J\x1b[H visible"
    assert _strip_ansi(with_cursor) == "visible"


def test_is_claude_ready_empty():
    assert _is_claude_ready("") is False


def test_is_claude_ready_no_prompt():
    assert _is_claude_ready("some output without the prompt character") is False


def test_is_claude_ready_with_prompt():
    pane = (
        "────────────────────────────────────────────────────────────────────\n"
        "❯\n"
        "────────────────────────────────────────────────────────────────────\n"
    )
    assert _is_claude_ready(pane) is True


def test_is_claude_ready_prompt_without_border():
    assert _is_claude_ready("❯ some line without any border around it") is False


def test_is_claude_ready_realistic():
    assert _is_claude_ready(REALISTIC_PANE) is True


def test_is_claude_ready_trust_prompt():
    assert _is_claude_ready(TRUST_PROMPT_PANE) is False
