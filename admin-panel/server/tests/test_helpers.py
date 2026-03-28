"""Tests for match_scope_pattern from helpers module."""
from core.helpers import match_scope_pattern


def test_match_scope_pattern_returnsTrue_whenExactFileMatch():
    assert match_scope_pattern("src/main.py", "src/main.py") is True


def test_match_scope_pattern_returnsFalse_whenDifferentFile():
    assert match_scope_pattern("src/other.py", "src/main.py") is False


def test_match_scope_pattern_returnsTrue_whenStarMatchesSingleLevel():
    assert match_scope_pattern("src/main.py", "src/*.py") is True


def test_match_scope_pattern_returnsFalse_whenStarDoesNotCrossDirs():
    assert match_scope_pattern("src/sub/main.py", "src/*.py") is False


def test_match_scope_pattern_returnsTrue_whenDoublestarMatchesRecursive():
    assert match_scope_pattern("src/a/b/c.py", "src/**") is True


def test_match_scope_pattern_returnsTrue_whenTrailingSlashMatchesDirectFile():
    assert match_scope_pattern("src/main.py", "src/") is True


def test_match_scope_pattern_returnsTrue_whenTrailingSlashMatchesNestedFile():
    assert match_scope_pattern("src/sub/file.py", "src/") is True


def test_match_scope_pattern_returnsFalse_whenFileOutsideDir():
    assert match_scope_pattern("other/file.py", "src/") is False


def test_match_scope_pattern_returnsTrue_whenDoublestarInMiddleMatches():
    assert match_scope_pattern("src/a/b/main.py", "src/**/main.py") is True


def test_match_scope_pattern_returnsFalse_whenEmptyPattern():
    assert match_scope_pattern("a/b/c.py", "") is False


def test_match_scope_pattern_returnsTrue_whenRootDoublestarMatchesPy():
    assert match_scope_pattern("a/b/c.py", "**/*.py") is True
