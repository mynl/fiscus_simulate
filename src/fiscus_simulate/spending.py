"""Spending liability: fixed category mix, constant inflation -> one nominal path (V1).

The household's real spending is split by a fixed category mix and inflated by each
category's constant rate (``pi_k = overall + excess_k``). Because inflation is
deterministic in V1, this is a single nominal path shared by every scenario.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import SPENDING_CATEGORIES, RunConfig
from .rates import annual_to_quarterly_return


@dataclass(frozen=True)
class SpendingPath:
    """Deterministic nominal spending over the horizon."""

    by_category: np.ndarray  # (T, K) in SPENDING_CATEGORIES order
    total: np.ndarray        # (T,)

    @property
    def housing_core_total(self) -> np.ndarray:
        """Nominal housing + core spending per period (essential-spending measure)."""
        idx = [i for i, c in enumerate(SPENDING_CATEGORIES) if c.value in ("housing", "core")]
        return self.by_category[:, idx].sum(axis=1)


def build_spending_path(config: RunConfig) -> SpendingPath:
    """Build the nominal quarterly spending path by category.

    Notes
    -----
    Base quarterly real spending per category is ``total_annual_real * pct/100 / 4``.
    Category inflation is applied by compounding a constant quarterly rate: period ``t``
    (0-indexed) carries factor ``(1 + pi_k_q) ** t`` — the first quarter is at today's
    prices.
    """
    T = config.household.n_periods
    sp = config.spending
    infl = config.inflation

    pct = np.array([sp.category_pct[c] for c in SPENDING_CATEGORIES]) / 100.0
    base_q_real = sp.total_annual_real * pct / 4.0  # (K,)

    annual_cat = np.array([infl.overall_mean + infl.category_excess_mean[c]
                           for c in SPENDING_CATEGORIES])
    q_cat = annual_to_quarterly_return(annual_cat)  # (K,)

    t = np.arange(T).reshape(-1, 1)                 # (T, 1)
    factors = np.power(1.0 + q_cat.reshape(1, -1), t)  # (T, K)
    by_category = base_q_real.reshape(1, -1) * factors
    return SpendingPath(by_category=by_category, total=by_category.sum(axis=1))
