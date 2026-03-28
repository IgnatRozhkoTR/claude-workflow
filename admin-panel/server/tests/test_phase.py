"""Tests for phase_key comparison utility."""
from core.phase import phase_key


def test_equality_same():
    assert phase_key("1.0") == phase_key("1.0")


def test_inequality():
    assert phase_key("1.0") != phase_key("2.0")


def test_ordering_major():
    assert phase_key("0") < phase_key("1.0")
    assert phase_key("2.0") < phase_key("3.1.0")
    assert phase_key("4.0") < phase_key("5")


def test_ordering_minor():
    assert phase_key("1.0") < phase_key("1.1")
    assert phase_key("1.2") < phase_key("1.3")


def test_ordering_sub():
    assert phase_key("3.1.0") < phase_key("3.1.4")
    assert phase_key("3.1.4") < phase_key("3.2.0")


def test_ordering_cross_depth():
    assert phase_key("3") < phase_key("3.0")
    assert phase_key("3.0") < phase_key("3.0.0")


def test_ordering_full_sequence():
    ordered = ["0", "1.0", "1.1", "1.2", "1.3", "2.0", "2.1",
               "3.1.0", "3.1.4", "3.2.0", "4.0", "4.1", "4.2", "5"]
    for i in range(len(ordered) - 1):
        assert phase_key(ordered[i]) < phase_key(ordered[i + 1]), \
            f"{ordered[i]} should be < {ordered[i + 1]}"


def test_gte():
    assert phase_key("3.0") >= phase_key("2.0")
    assert phase_key("2.0") >= phase_key("2.0")


def test_lte():
    assert phase_key("1.3") <= phase_key("2.0")
    assert phase_key("2.0") <= phase_key("2.0")


def test_gt():
    assert phase_key("3.1.4") > phase_key("2.1")


def test_tuple_structure():
    assert phase_key("3.1.4") == (3, 1, 4)
    assert phase_key("1.0") == (1, 0)
    assert phase_key("5") == (5,)
