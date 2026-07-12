"""Summary statistics, percentile trajectories, and failure summaries.

Reduces a run's per-scenario results to compact, chart-ready aggregates. Percentile
trajectories drive the net-worth funnel; stored nominal, with a ``deflator`` so the web
layer can toggle real/nominal without recomputing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

def _tail_refined_pcts() -> tuple[float, ...]:
    """Symmetric, tail-dense percentile grid (percent): p0.1 … p99.9.

    Notes
    -----
    Dense in the tails, coarse in the middle — where the action is for ruin analysis:
    0.1→1 by 0.1, 1→10 by 1, 10→90 by 10, 90→99 by 1, 99→99.9 by 0.1 (deduped endpoints).
    """
    lo_tenths = [round(0.1 * i, 1) for i in range(1, 10)]      # 0.1 .. 0.9
    ones_lo = [float(v) for v in range(1, 11)]                 # 1 .. 10
    tens = [float(v) for v in range(20, 91, 10)]               # 20 .. 90
    ones_hi = [float(v) for v in range(91, 100)]               # 91 .. 99
    hi_tenths = [round(99 + 0.1 * i, 1) for i in range(1, 10)]  # 99.1 .. 99.9
    return tuple(sorted(set(lo_tenths + ones_lo + tens + ones_hi + hi_tenths)))


PCTS: tuple[float, ...] = _tail_refined_pcts()


@dataclass
class SimulationSummary:
    """Compact summary of a simulation run (NumPy arrays; no per-path cube)."""

    n_scenarios: int
    percentiles: tuple[float, ...]
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
    scalar_means: dict[str, float] = field(default_factory=dict)
    joint_by_terminal: dict[str, np.ndarray] = field(default_factory=dict)
    terminal_hist_edges: np.ndarray = field(default_factory=lambda: np.zeros(0))  # (n_bin+1,)
    terminal_hist_counts: np.ndarray = field(default_factory=lambda: np.zeros(0))  # (n_bin,)

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
    # Marginal percentiles: each column sorted independently (a p50 of tax and a p50 of
    # terminal wealth generally come from *different* scenarios).
    scalar_pctiles = {
        "terminal_nominal": term_nom,
        "min_net_worth": np.percentile(min_net_worth, pcts),
        "years_funded": np.percentile(years_funded, pcts),
        "total_tax": np.percentile(total_tax, pcts),
        "total_sales": np.percentile(total_sales, pcts),
    }

    # Means (order-independent, so shared by both table views).
    scalar_means = {
        "terminal_nominal": float(terminal_net_worth.mean()),
        "min_net_worth": float(min_net_worth.mean()),
        "years_funded": float(years_funded.mean()),
        "total_tax": float(total_tax.mean()),
        "total_sales": float(total_sales.mean()),
    }

    # Joint view: the actual scenarios ranked by terminal net worth. Each percentile row
    # is ONE real path, so a row reads across coherently (the median-terminal-wealth
    # household's own taxes, sales, funded years, ...).
    order = np.argsort(terminal_net_worth, kind="stable")
    ranks = np.clip(np.round(pcts / 100.0 * (S - 1)).astype(int), 0, S - 1)
    idx = order[ranks]
    joint_by_terminal = {
        "terminal_nominal": terminal_net_worth[idx],
        "min_net_worth": min_net_worth[idx],
        "years_funded": years_funded[idx],
        "total_tax": total_tax[idx],
        "total_sales": total_sales[idx],
    }

    # Terminal-wealth histogram for the results chart. Clip both tails (1st/99th pct) into
    # the end bins so outliers — including deep-debt ruin — don't squash the visible mass.
    hist_lo = min(0.0, float(np.percentile(terminal_net_worth, 1)))
    hist_hi = float(np.percentile(terminal_net_worth, 99))
    if hist_hi <= hist_lo:  # degenerate (all equal) — nudge so histogram has width
        hist_hi = hist_lo + 1.0
    clipped = np.clip(terminal_net_worth, hist_lo, hist_hi)
    hist_counts, hist_edges = np.histogram(clipped, bins=40, range=(hist_lo, hist_hi))

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
        scalar_means=scalar_means,
        joint_by_terminal=joint_by_terminal,
        terminal_hist_edges=hist_edges,
        terminal_hist_counts=hist_counts,
    )
