"""V1 correlated GBM / lognormal return generator for stocks, bonds, cash.

Per asset and quarter the real total return is lognormal; assets are correlated via the
config correlation matrix; inflation is constant (V1); income yield is deterministic.

Conventions (see ``dev/plan-1.2-stage3-returns.md`` §2):
- Quarterly vol ``s_q = sigma_annual * sqrt(1/4)``.
- Log-return centered so the **geometric** quarterly real mean equals the deterministic
  figure ``g_q = (1+r_real_annual)^(1/4) - 1`` — i.e. at ``sigma = 0`` this generator
  reduces exactly to the deterministic provider.
- ``nominal_total = (1+q_real)(1+pi_q) - 1``; ``income_yield = annual_yield/4``;
  ``capital_return = nominal_total - income_yield``.
"""
from __future__ import annotations

import numpy as np

from ..models import ASSET_CLASSES, RunConfig
from ..rates import annual_to_quarterly_return, annual_to_quarterly_yield
from .base import ReturnGenerator, ReturnsBundle


class GBMReturns(ReturnGenerator):
    """Correlated multivariate lognormal (GBM) real returns; constant inflation/yield."""

    def __init__(self, config: RunConfig) -> None:
        super().__init__(config)
        rg = config.return_generator
        self._real = np.array([rg.real_return[a] for a in ASSET_CLASSES])
        self._sigma_annual = np.array([rg.volatility[a] for a in ASSET_CLASSES])
        self._yld = np.array([rg.income_yield[a] for a in ASSET_CLASSES])
        corr = np.array(rg.correlations, dtype=float)
        try:
            self._chol = np.linalg.cholesky(corr)
        except np.linalg.LinAlgError as exc:  # pragma: no cover - config guard
            raise ValueError(
                "return correlation matrix is not positive semi-definite; "
                "adjust the correlations (nearest-PSD repair is a future feature)"
            ) from exc

    def generate(self, n_scenarios: int) -> ReturnsBundle:
        cfg = self.config
        T = cfg.household.n_periods
        n_asset = len(ASSET_CLASSES)
        pi_q = float(annual_to_quarterly_return(cfg.inflation.overall_mean))

        s_q = self._sigma_annual * np.sqrt(0.25)                 # (n_asset,)
        g_q = annual_to_quarterly_return(self._real)             # (n_asset,) geometric mean
        m = np.log1p(g_q)                                        # log-return mean

        rng = np.random.default_rng(cfg.simulation.seed)
        z = rng.standard_normal((n_scenarios, T, n_asset))
        z = z @ self._chol.T                                     # impose correlation
        x = m[None, None, :] + s_q[None, None, :] * z            # log real return
        q_real = np.expm1(x)                                     # exp(x) - 1

        nominal_total = (1.0 + q_real) * (1.0 + pi_q) - 1.0
        q_yield = annual_to_quarterly_yield(self._yld)
        income_yield = np.broadcast_to(
            q_yield.reshape(1, 1, -1), (n_scenarios, T, n_asset)
        ).copy()
        capital_return = nominal_total - income_yield

        return ReturnsBundle(
            capital_return=capital_return,
            income_yield=income_yield,
            nominal_total=nominal_total,
            overall_inflation_q=pi_q,
        )
