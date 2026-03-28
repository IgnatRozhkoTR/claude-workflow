"""Tests for PhaseId comparator."""
from core.phase import PhaseId as Phase


def test_equality_same():
    assert Phase("1.0") == Phase("1.0")


def test_equality_string():
    assert Phase("1.0") == "1.0"


def test_inequality():
    assert Phase("1.0") != Phase("2.0")


def test_ordering_major():
    assert Phase("0") < Phase("1.0")
    assert Phase("2.0") < Phase("3.1.0")
    assert Phase("4.0") < Phase("5")


def test_ordering_minor():
    assert Phase("1.0") < Phase("1.1")
    assert Phase("1.2") < Phase("1.3")


def test_ordering_sub():
    assert Phase("3.1.0") < Phase("3.1.4")
    assert Phase("3.1.4") < Phase("3.2.0")


def test_ordering_cross_depth():
    assert Phase("3") < Phase("3.0")
    assert Phase("3.0") < Phase("3.0.0")


def test_ordering_full_sequence():
    ordered = ["0", "1.0", "1.1", "1.2", "1.3", "2.0", "2.1",
               "3.1.0", "3.1.4", "3.2.0", "4.0", "4.1", "4.2", "5"]
    for i in range(len(ordered) - 1):
        assert Phase(ordered[i]) < Phase(ordered[i + 1]), f"{ordered[i]} should be < {ordered[i+1]}"


def test_gte_string():
    assert Phase("3.0") >= "2.0"
    assert Phase("2.0") >= "2.0"


def test_lte_string():
    assert Phase("1.3") <= "2.0"
    assert Phase("2.0") <= "2.0"


def test_gt_string():
    assert Phase("3.1.4") > "2.1"


def test_hash_equal():
    assert hash(Phase("1.0")) == hash(Phase("1.0"))


def test_hash_in_set():
    s = {Phase("1.0"), Phase("2.0")}
    assert Phase("1.0") in s
    assert Phase("3.0") not in s


def test_str():
    assert str(Phase("3.1.4")) == "3.1.4"


def test_repr():
    assert repr(Phase("3.1.4")) == "PhaseId('3.1.4')"


def test_copy_constructor():
    p = Phase("2.1")
    assert Phase(p) == p


def test_non_phase_comparison():
    assert Phase("1.0").__eq__(42) is NotImplemented
    assert Phase("1.0").__lt__(42) is NotImplemented
