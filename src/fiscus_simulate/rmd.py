"""Required minimum distributions (RMDs) — IRS Uniform Lifetime Table.

V1 models RMDs on the pooled tax-deferred balance: once a person reaches the configured
``rmd_start_age`` (SECURE Act 2.0: 73 for those born 1951-1959, 75 for born 1960+), each
year they must withdraw at least ``balance / divisor(age)`` from tax-deferred accounts,
taxed as ordinary income on withdrawal. The divisor comes from the IRS Uniform Lifetime
Table (post-2021). Ages beyond the table use the age-120 divisor.

This is a compact, transparent stand-in — the table is public and fixed — not tax advice.
Per-person account attribution is a V1 simplification (accounts are pooled): the household
RMD applies once the eldest reaches ``rmd_start_age``.
"""
from __future__ import annotations

import math

# IRS Uniform Lifetime Table (used for RMDs from 2022 on). age -> distribution period.
UNIFORM_LIFETIME: dict[int, float] = {
    72: 27.4, 73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0, 79: 21.1,
    80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7, 84: 16.8, 85: 16.0, 86: 15.2, 87: 14.4,
    88: 13.7, 89: 12.9, 90: 12.2, 91: 11.5, 92: 10.8, 93: 10.1, 94: 9.5, 95: 8.9,
    96: 8.4, 97: 7.8, 98: 7.3, 99: 6.8, 100: 6.4, 101: 6.0, 102: 5.6, 103: 5.2,
    104: 4.9, 105: 4.6, 106: 4.3, 107: 4.1, 108: 3.9, 109: 3.7, 110: 3.5, 111: 3.4,
    112: 3.3, 113: 3.1, 114: 3.0, 115: 2.9, 116: 2.8, 117: 2.7, 118: 2.5, 119: 2.3,
    120: 2.0,
}

_MIN_AGE = min(UNIFORM_LIFETIME)
_MAX_AGE = max(UNIFORM_LIFETIME)


def rmd_divisor(age: float) -> float | None:
    """Uniform Lifetime distribution period for ``age`` (``None`` below the table).

    Parameters
    ----------
    age : float
        Age in years; floored to a whole year for the lookup.

    Returns
    -------
    float or None
        The distribution period (``balance / divisor`` is the year's RMD), the age-120
        value for ages past the table, or ``None`` for ages below it (no RMD).
    """
    a = int(math.floor(age))
    if a < _MIN_AGE:
        return None
    return UNIFORM_LIFETIME[min(a, _MAX_AGE)]


def rmd_fraction(age: float) -> float:
    """Fraction of the tax-deferred balance due as this year's RMD (0 below the table)."""
    divisor = rmd_divisor(age)
    return 0.0 if divisor is None else 1.0 / divisor
