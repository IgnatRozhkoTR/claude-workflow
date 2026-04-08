"""Smoke tests for commit history panel frontend markup."""
from pathlib import Path

import pytest
from bs4 import BeautifulSoup


TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


@pytest.fixture(scope="module")
def html():
    return BeautifulSoup((TEMPLATES_DIR / "admin.html").read_text(), "html.parser")


def test_commit_toggle_button_exists(html):
    btn = html.find("button", attrs={"data-mode": "commit"})
    assert btn is not None, "Commit toggle button not found"
    assert "setDiffSource('commit')" in (btn.get("onclick") or "")


def test_history_toggle_button_exists(html):
    btn = html.find("button", attrs={"id": "historyToggleBtn"})
    assert btn is not None, "historyToggleBtn button not found"
    assert "toggleHistoryPanel()" in (btn.get("onclick") or "")


def test_diff_history_panel_exists(html):
    panel = html.find("div", attrs={"id": "diffHistoryPanel"})
    assert panel is not None, "diffHistoryPanel not found"


def test_diff_history_panel_header_exists(html):
    panel = html.find("div", attrs={"id": "diffHistoryPanel"})
    assert panel is not None
    header = panel.find("div", class_="diff-history-panel-header")
    assert header is not None, "diff-history-panel-header not found inside panel"


def test_diff_history_list_exists(html):
    panel = html.find("div", attrs={"id": "diffHistoryPanel"})
    assert panel is not None
    lst = panel.find("div", attrs={"id": "diffHistoryList"})
    assert lst is not None, "diffHistoryList not found inside panel"


def test_diff_history_selection_count_exists(html):
    count = html.find("span", attrs={"id": "diffHistorySelectionCount"})
    assert count is not None, "diffHistorySelectionCount badge not found"


def test_diff_history_branch_label_exists(html):
    label = html.find("span", attrs={"id": "diffHistoryBranchLabel"})
    assert label is not None, "diffHistoryBranchLabel not found"


def test_diff_history_close_button_exists(html):
    panel = html.find("div", attrs={"id": "diffHistoryPanel"})
    assert panel is not None
    close_btn = panel.find("button", attrs={"onclick": "closeHistoryPanel()"})
    assert close_btn is not None, "Close button not found inside history panel"


def test_diff_history_actions_area_exists(html):
    panel = html.find("div", attrs={"id": "diffHistoryPanel"})
    assert panel is not None
    actions = panel.find("div", class_="diff-history-panel-actions")
    assert actions is not None, "diff-history-panel-actions toolbar area not found"
