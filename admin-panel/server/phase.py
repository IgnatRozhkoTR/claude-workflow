"""Phase value object for ordinal phase comparison."""
from functools import total_ordering


@total_ordering
class Phase:
    """Comparable phase identifier.

    Splits a dotted phase string (e.g. '3.1.4') into integer segments
    and compares segment-by-segment: Phase('3.1.4') > Phase('2.1').
    Accepts raw strings on the right-hand side of operators.
    """

    __slots__ = ("_parts",)

    def __init__(self, value):
        if isinstance(value, Phase):
            self._parts = value._parts
        else:
            self._parts = tuple(int(x) for x in str(value).split("."))

    def __eq__(self, other):
        if isinstance(other, str):
            other = Phase(other)
        if not isinstance(other, Phase):
            return NotImplemented
        return self._parts == other._parts

    def __lt__(self, other):
        if isinstance(other, str):
            other = Phase(other)
        if not isinstance(other, Phase):
            return NotImplemented
        return self._parts < other._parts

    def __hash__(self):
        return hash(self._parts)

    def __str__(self):
        return ".".join(str(x) for x in self._parts)

    def __repr__(self):
        return f"Phase('{self}')"