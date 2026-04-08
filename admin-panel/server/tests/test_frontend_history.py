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


def test_rename_button_exists_and_wired(html):
    btn = html.find("button", attrs={"id": "historyRenameBtn"})
    assert btn is not None, "historyRenameBtn not found"
    assert "historyRename()" in (btn.get("onclick") or ""), "historyRenameBtn must call historyRename()"
    assert btn.get("disabled") is not None, "historyRenameBtn must start disabled"


def test_undo_button_exists_and_wired(html):
    btn = html.find("button", attrs={"id": "historyUndoBtn"})
    assert btn is not None, "historyUndoBtn not found"
    assert "historyUndo()" in (btn.get("onclick") or ""), "historyUndoBtn must call historyUndo()"
    assert btn.get("disabled") is not None, "historyUndoBtn must start disabled"


def test_squash_button_exists_and_wired(html):
    btn = html.find("button", attrs={"id": "historySquashBtn"})
    assert btn is not None, "historySquashBtn not found"
    assert "historySquash()" in (btn.get("onclick") or ""), "historySquashBtn must call historySquash()"
    assert btn.get("disabled") is not None, "historySquashBtn must start disabled"


def test_rewrite_buttons_have_i18n_keys(html):
    rename_btn = html.find("button", attrs={"id": "historyRenameBtn"})
    undo_btn = html.find("button", attrs={"id": "historyUndoBtn"})
    squash_btn = html.find("button", attrs={"id": "historySquashBtn"})
    assert rename_btn is not None
    assert undo_btn is not None
    assert squash_btn is not None
    assert rename_btn.get("data-i18n") == "history.rename", "historyRenameBtn must have data-i18n='history.rename'"
    assert undo_btn.get("data-i18n") == "history.undo", "historyUndoBtn must have data-i18n='history.undo'"
    assert squash_btn.get("data-i18n") == "history.squash", "historySquashBtn must have data-i18n='history.squash'"


def test_rewrite_buttons_inside_actions_area(html):
    panel = html.find("div", attrs={"id": "diffHistoryPanel"})
    assert panel is not None
    actions = panel.find("div", class_="diff-history-panel-actions")
    assert actions is not None
    btn_ids = {btn.get("id") for btn in actions.find_all("button")}
    assert "historyRenameBtn" in btn_ids, "historyRenameBtn must be inside diff-history-panel-actions"
    assert "historyUndoBtn" in btn_ids, "historyUndoBtn must be inside diff-history-panel-actions"
    assert "historySquashBtn" in btn_ids, "historySquashBtn must be inside diff-history-panel-actions"
