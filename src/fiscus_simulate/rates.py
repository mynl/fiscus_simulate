"""Annual <-> quarterly rate conversions and the real->nominal identity.

Conventions (confirmed 2026-07-07, see ``dev/plan-1.1-stage2-engine.md`` §4):

- **Returns and inflation** convert **geometrically**: a quarterly rate that compounds
  to the stated annual figure over four quarters, ``(1 + a) ** (1/4) - 1``.
- **Income yields** convert **simply**: ``a / 4`` (a documented choice — yield is a
  distribution rate, not a compounding growth rate).
- **Real to nominal**: ``1 + R_nominal = (1 + r_real)(1 + pi)``.

These are pure, vectorized (accept floats or NumPy arrays), and unit-tested.
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "annual_to_quarterly_return",
    "annual_to_quarterly_yield",
    "real_to_nominal",
]


def annual_to_quarterly_return(annual):
    """Quarterly compounding-equivalent of an annual return/inflation rate."""
    return np.power(1.0 + np.asarray(annual, dtype=float), 0.25) - 1.0


def annual_to_quarterly_yield(annual):
    """Quarterly income yield from an annual yield (simple division by 4)."""
    return np.asarray(annual, dtype=float) / 4.0


def real_to_nominal(real, inflation):
    """Nominal total return from a real return and inflation: ``(1+r)(1+pi) - 1``."""
    r = np.asarray(real, dtype=float)
    pi = np.asarray(inflation, dtype=float)
    return (1.0 + r) * (1.0 + pi) - 1.0
