"""Pre-retirement savings contributions (real $/yr per person, pooled).

Each person contributes ``annual_real_savings`` (real, today's money) each year until
they reach their ``retirement_age``. Amounts convert to quarterly (``/4``) and are
inflated to nominal by overall inflation — the same convention as inflation-linked
income streams — so a constant real saving is a growing nominal contribution.

The engine invests these contributions in the taxable account at the current portfolio
allocation, with cost basis stepped up (bought at market). See the engine's order of
operations. A single household path shares this schedule (it does not depend on returns).
"""
from __future__ import annotations

import numpy as np

from .models import RunConfig


def build_savings_path(config: RunConfig, overall_inflation_q: float) -> np.ndarray:
    """Nominal savings inflow per quarter, ``(T,)`` (summed over working people).

    Parameters
    ----------
    overall_inflation_q : float
        Constant quarterly overall inflation, used to index real contributions to nominal.
    """
    T = config.household.n_periods
    t = np.arange(T)
    infl_factor = np.power(1.0 + overall_inflation_q, t)

    total = np.zeros(T)
    for person in config.household.people:
        if person.annual_real_savings <= 0 or person.retirement_age is None:
            continue
        working = t < person.retirement_period()
        total += np.where(working, person.annual_real_savings / 4.0, 0.0) * infl_factor
    return total
