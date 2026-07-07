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

Chunking: :meth:`iter_chunks` streams from a single RNG so the concatenation of chunks is
bit-identical to one :meth:`generate` of the full count (Stage 4 memory discipline).
"""
from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from ..models import ASSET_CLASSES, RunConfig
from ..rates import annual_to_quarterly_return, annual_to_quarterly_yield
from .base import ReturnGenerator, ReturnsBundle


class GBMReturns(ReturnGenerator):
    """Correlated multivariate lognormal (GBM) real returns; constant inflation/yield."""

    def __init__(self, config: RunConfig) -> None:
        super().__init__(config)
        rg = config.return_generator
        real = np.array([rg.real_return[a] for a in ASSET_CLASSES])
        sigma_annual = np.array([rg.volatility[a] for a in ASSET_CLASSES])
        yld = np.array([rg.income_yield[a] for a in ASSET_CLASSES])

        self._T = config.household.n_periods
        self._n_asset = len(ASSET_CLASSES)
        self._seed = config.simulation.seed
        self._pi_q = float(annual_to_quarterly_return(config.inflation.overall_mean))
        self._s_q = sigma_annual * np.sqrt(0.25)
        self._m = np.log1p(annual_to_quarterly_return(real))  # geometric-mean centering
        self._q_yield = annual_to_quarterly_yield(yld)

        corr = np.array(rg.correlations, dtype=float)
        try:
            self._chol = np.linalg.cholesky(corr)
        except np.linalg.LinAlgError as exc:  # pragma: no cover - config guard
            raise ValueError(
                "return correlation matrix is not positive semi-definite; "
                "adjust the correlations (nearest-PSD repair is a future feature)"
            ) from exc

    def _bundle_from_z(self, z: np.ndarray) -> ReturnsBundle:
        """Build a bundle from standard-normal draws ``z`` of shape ``(S, T, n_asset)``."""
        s = z.shape[0]
        z = z @ self._chol.T                                  # impose correlation
        x = self._m[None, None, :] + self._s_q[None, None, :] * z
        q_real = np.expm1(x)
        nominal_total = (1.0 + q_real) * (1.0 + self._pi_q) - 1.0
        income_yield = np.broadcast_to(
            self._q_yield.reshape(1, 1, -1), (s, self._T, self._n_asset)
        ).copy()
        return ReturnsBundle(
            capital_return=nominal_total - income_yield,
            income_yield=income_yield,
            nominal_total=nominal_total,
            overall_inflation_q=self._pi_q,
        )

    def generate(self, n_scenarios: int) -> ReturnsBundle:
        rng = np.random.default_rng(self._seed)
        return self._bundle_from_z(rng.standard_normal((n_scenarios, self._T, self._n_asset)))

    def iter_chunks(self, n_scenarios: int, chunk_size: int) -> Iterator[ReturnsBundle]:
        """Stream bundles summing to ``n_scenarios`` (bit-identical to one ``generate``)."""
        rng = np.random.default_rng(self._seed)
        done = 0
        while done < n_scenarios:
            c = min(chunk_size, n_scenarios - done)
            yield self._bundle_from_z(rng.standard_normal((c, self._T, self._n_asset)))
            done += c
