"""Phase string comparison utilities.

Used by services and other packages that need to compare phase strings
without depending on the advance package. The Phase ABC in advance/phases/
owns the full comparison behavior for Phase objects.
"""


def phase_key(phase_str: str) -> tuple[int, ...]:
    """Parse a dotted phase string into a comparable tuple.

    >>> phase_key("3.1.4")
    (3, 1, 4)
    """
    return tuple(int(x) for x in phase_str.split('.'))
