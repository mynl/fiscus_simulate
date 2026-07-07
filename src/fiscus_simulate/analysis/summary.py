"""Summary statistics, percentile trajectories, and failure summaries.

Reduces a run's per-scenario results to compact, chart-ready aggregates. Percentile
trajectories drive the net-worth funnel; stored nominal, with a ``deflator`` so the web
layer can toggle real/nominal without recomputing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

PCTS: tuple[int, ...] = (1, 5, 10, 25, 50, 75, 90, 95, 99)


@dataclass
class SimulationSummary:
    """Compact summary of a simulation run (NumPy arrays; no per-path cube)."""

    n_scenarios: int
    percentiles: tuple[int, ...]
    success_rates: dict[str, float]
    overall_success_rate: float
    failure_timing: np.ndarray            # (T,) count of paths whose first failure is at t
    n_never_fail: int
    net_worth_pctiles_nominal: np.ndarray  # (n_pct, T)
    deflator: np.ndarray                   # (T,) nominal -> real divisor
    terminal_stats: dict[str, float]
    terminal_pctiles_nominal: np.ndarray   # (n_pct,)
    terminal_pctiles_real: np.ndarray      # (n_pct,)
    scalar_pctiles: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def net_worth_pctiles_real(self) -> np.ndarray:
        """Real (today's-money) percentile trajectories, ``(n_pct, T)``."""
        return self.net_worth_pctiles_nominal / self.deflator[None, :]


def summarize(
    net_worth: np.ndarray,
    min_net_worth: np.ndarray,
    terminal_net_worth: np.ndarray,
    years_funded: np.ndarray,
    first_failure_period: np.ndarray,
    total_tax: np.ndarray,
    total_sales: np.ndarray,
    success: dict[str, np.ndarray],
    overall_inflation_q: float,
) -> SimulationSummary:
    """Build a :class:`SimulationSummary` from per-scenario arrays.

    Parameters
    ----------
    net_worth : ndarray, shape (S, T)
        End-of-period nominal net worth per path (the only full-size array).
    min_net_worth, terminal_net_worth, years_funded, first_failure_period, total_tax, \
    total_sales : ndarray, shape (S,)
        Per-path scalar outcomes; ``first_failure_period`` is ``-1`` where never failed.
    success : dict of ndarray
        Boolean ``(S,)`` arrays per success criterion.
    overall_inflation_q : float
        Constant quarterly overall inflation, for the real/nominal deflator.
    """
    S, T = net_worth.shape
    pcts = np.array(PCTS)

    success_rates = {k: float(v.mean()) for k, v in success.items()}
    overall = np.ones(S, dtype=bool)
    for v in success.values():
        overall &= v
    overall_rate = float(overall.mean())

    failed = first_failure_period >= 0
    failure_timing = np.bincount(first_failure_period[failed], minlength=T)[:T].astype(int)
    n_never_fail = int((~failed).sum())

    deflator = np.power(1.0 + overall_inflation_q, np.arange(1, T + 1))

    nw_pctiles = np.percentile(net_worth, pcts, axis=0)  # (n_pct, T)
    term_nom = np.percentile(terminal_net_worth, pcts)
    term_real = term_nom / deflator[-1]

    terminal_stats = {
        "mean": float(terminal_net_worth.mean()),
        "std": float(terminal_net_worth.std()),
        "min": float(terminal_net_worth.min()),
        "max": float(terminal_net_worth.max()),
    }
    scalar_pctiles = {
        "min_net_worth": np.percentile(min_net_worth, pcts),
        "years_funded": np.percentile(years_funded, pcts),
        "total_tax": np.percentile(total_tax, pcts),
        "total_sales": np.percentile(total_sales, pcts),
    }

    return SimulationSummary(
        n_scenarios=S,
        percentiles=PCTS,
        success_rates=success_rates,
        overall_success_rate=overall_rate,
        failure_timing=failure_timing,
        n_never_fail=n_never_fail,
        net_worth_pctiles_nominal=nw_pctiles,
        deflator=deflator,
        terminal_stats=terminal_stats,
        terminal_pctiles_nominal=term_nom,
        terminal_pctiles_real=term_real,
        scalar_pctiles=scalar_pctiles,
    )
