"""RMD Uniform Lifetime Table lookups (1.9.0 primitive)."""
from __future__ import annotations

import math

from fiscus_simulate.rmd import rmd_divisor, rmd_fraction


def test_divisor_lookups():
    assert rmd_divisor(73) == 26.5
    assert rmd_divisor(75) == 24.6      # default RMD age
    assert rmd_divisor(80) == 20.2


def test_below_table_is_none():
    assert rmd_divisor(70) is None
    assert rmd_divisor(71) is None
    assert rmd_divisor(72.9) == 27.4    # floored to 72, the first table entry


def test_above_table_clamps_to_120():
    assert rmd_divisor(120) == 2.0
    assert rmd_divisor(135) == 2.0


def test_fraction():
    assert math.isclose(rmd_fraction(75), 1.0 / 24.6)
    assert rmd_fraction(70) == 0.0      # no RMD below the table
