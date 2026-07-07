"""Deterministic (constant) return provider.

Produces the same per-asset quarterly capital return and income yield every period,
derived from the config's real returns + constant inflation. Arrays carry a scenario
axis of size 1 (broadcast over scenarios). Stage 3's GBM generator returns the same
:class:`ReturnsBundle` contract with a full scenario axis.
"""
from __future__ import annotations

import numpy as np

from ..models import ASSET_CLASSES, RunConfig
from ..rates import annual_to_quarterly_return, annual_to_quarterly_yield, real_to_nominal
from .base import ReturnGenerator, ReturnsBundle


def build_deterministic_returns(config: RunConfig) -> ReturnsBundle:
    """Build constant quarterly return arrays ``(1, T, n_asset)`` from ``config``.

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

    q_total = annual_to_quarterly_return(real_to_nominal(real, pi))  # (n_asset,)
    q_yield = annual_to_quarterly_yield(yld)
    q_capital = q_total - q_yield

    def _spread(vec: np.ndarray) -> np.ndarray:
        return np.tile(vec, (1, T, 1))  # (1, T, n_asset)

    v = lambda x: x.reshape(1, 1, -1)  # noqa: E731
    return ReturnsBundle(
        capital_return=_spread(v(q_capital)),
        income_yield=_spread(v(q_yield)),
        nominal_total=_spread(v(q_total)),
        overall_inflation_q=float(annual_to_quarterly_return(pi)),
    )


class DeterministicReturns(ReturnGenerator):
    """Generator wrapper around :func:`build_deterministic_returns`.

    All scenarios are identical, so the size-1 arrays are broadcast (read-only views —
    the engine only reads them) up to ``n_scenarios`` with no extra memory.
    """

    def generate(self, n_scenarios: int = 1) -> ReturnsBundle:
        b = build_deterministic_returns(self.config)  # (1, T, n_asset)
        if n_scenarios == 1:
            return b

        def bc(a: np.ndarray) -> np.ndarray:
            return np.broadcast_to(a, (n_scenarios,) + a.shape[1:])

        return ReturnsBundle(
            capital_return=bc(b.capital_return),
            income_yield=bc(b.income_yield),
            nominal_total=bc(b.nominal_total),
            overall_inflation_q=b.overall_inflation_q,
        )
