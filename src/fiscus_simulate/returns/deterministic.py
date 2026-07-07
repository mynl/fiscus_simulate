"""Deterministic (constant) return provider for the Stage 2 engine.

Produces the same per-asset quarterly capital return and income yield every period,
derived from the config's real returns + constant inflation. Stage 3 replaces this with
the stochastic GBM generator behind the same array contract:
``capital_return`` and ``income_yield`` shaped ``(T, n_assets)`` in ``ASSET_CLASSES``
order, plus the constant quarterly overall inflation used to index income/spending.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..models import ASSET_CLASSES, RunConfig
from ..rates import annual_to_quarterly_return, annual_to_quarterly_yield, real_to_nominal


@dataclass(frozen=True)
class ReturnsBundle:
    """Per-period quarterly return arrays (``ASSET_CLASSES`` column order)."""

    capital_return: np.ndarray  # (T, n_assets)
    income_yield: np.ndarray    # (T, n_assets)
    overall_inflation_q: float  # constant quarterly overall inflation


def build_deterministic_returns(config: RunConfig) -> ReturnsBundle:
    """Build constant quarterly capital-return and yield arrays from ``config``.

    Notes
    -----
    Nominal total return per asset is ``(1+r_real)(1+pi)-1`` (annual), converted to a
    quarterly compounding-equivalent. Income yield converts as ``annual/4``. The capital
    return is the residual ``q_total - q_yield`` (additive split; documented convention).
    """
    rg = config.return_generator
    pi = config.inflation.overall_mean
    T = config.household.n_periods

    real = np.array([rg.real_return[a] for a in ASSET_CLASSES])
    yld = np.array([rg.income_yield[a] for a in ASSET_CLASSES])

    annual_nominal_total = real_to_nominal(real, pi)
    q_total = annual_to_quarterly_return(annual_nominal_total)
    q_yield = annual_to_quarterly_yield(yld)
    q_capital = q_total - q_yield

    capital = np.tile(q_capital, (T, 1))
    income = np.tile(q_yield, (T, 1))
    return ReturnsBundle(
        capital_return=capital,
        income_yield=income,
        overall_inflation_q=float(annual_to_quarterly_return(pi)),
    )
