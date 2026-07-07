"""Service layer: the only seam between the web layer and the engine.

Runs a simulation in scenario chunks (so the full return cube never lives in memory),
aggregates per-scenario outcomes, and reduces them to a compact
:class:`~fiscus_simulate.analysis.summary.SimulationSummary` plus a bounded set of
representative paths. Keeps Flask out of the engine and the engine out of Flask.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import numpy as np

from .analysis.summary import SimulationSummary, summarize
from .engine import simulate
from .models import RunConfig
from .returns.base import ReturnGenerator
from .returns.deterministic import DeterministicReturns
from .returns.gbm import GBMReturns

# Success-criterion keys (must match EngineResult.success()).
CRITERIA = (
    "portfolio_non_negative",
    "essential_funded",
    "all_planned_funded",
    "terminal_above_threshold",
)
DEFAULT_SAMPLE_PATHS = 20


@dataclass
class SimulationResult:
    """Everything the web/persistence layers need from a run — no per-path cube."""

    summary: SimulationSummary
    sample_paths: dict          # {'net_worth': (k, T), 'success': (k,) bool, 'index': (k,)}
    meta: dict


def make_generator(config: RunConfig) -> ReturnGenerator:
    """Return the generator named by ``config.return_generator.kind``."""
    kind = config.return_generator.kind
    if kind == "gbm":
        return GBMReturns(config)
    if kind in ("deterministic", "constant"):
        return DeterministicReturns(config)
    raise ValueError(f"unknown return generator kind: {kind!r}")


def run_simulation(config: RunConfig, generator: ReturnGenerator | None = None,
                   persist: bool = False, runs_dir=None) -> SimulationResult:
    """Run the full simulation in chunks and summarize it.

    Parameters
    ----------
    config : RunConfig
        The run configuration.
    generator : ReturnGenerator, optional
        Override the generator (defaults to :func:`make_generator`).
    persist : bool
        When True, save the run to a directory (``runs_dir`` or the app-state default)
        and record ``run_id`` / ``run_dir`` in ``meta``.
    runs_dir : Path, optional
        Parent directory for the saved run.
    """
    gen = generator or make_generator(config)
    S = config.simulation.n_scenarios
    T = config.household.n_periods
    chunk = config.simulation.chunk_size

    net_worth = np.empty((S, T))
    min_nw = np.empty(S)
    terminal = np.empty(S)
    years = np.empty(S)
    first_fail = np.empty(S, dtype=int)
    total_tax = np.empty(S)
    total_sales = np.empty(S)
    success = {k: np.empty(S, dtype=bool) for k in CRITERIA}

    pi_q = 0.0
    offset = 0
    t0 = perf_counter()
    for bundle in gen.iter_chunks(S, chunk):
        res = simulate(config, returns=bundle)
        c = res.net_worth.shape[0]
        sl = slice(offset, offset + c)
        net_worth[sl] = res.net_worth
        min_nw[sl] = res.min_net_worth
        terminal[sl] = res.terminal_net_worth
        years[sl] = res.years_funded
        first_fail[sl] = res.first_failure_period
        total_tax[sl] = res.total_tax
        total_sales[sl] = res.total_sales
        s = res.success()
        for k in CRITERIA:
            success[k][sl] = s[k]
        pi_q = bundle.overall_inflation_q
        offset += c
    runtime = perf_counter() - t0

    if offset != S:  # pragma: no cover - guards a generator that under/over-fills
        raise RuntimeError(f"generator produced {offset} scenarios, expected {S}")

    summary = summarize(net_worth, min_nw, terminal, years, first_fail,
                        total_tax, total_sales, success, pi_q)
    sample = _representative(net_worth, success)
    meta = {
        "n_scenarios": S,
        "seed": config.simulation.seed,
        "generator": config.return_generator.kind,
        "chunk_size": chunk,
        "runtime_s": runtime,
    }
    result = SimulationResult(summary=summary, sample_paths=sample, meta=meta)

    if persist:
        from .storage import save_run  # lazy: keeps non-persisted runs pandas-free
        run_dir = save_run(result, config, runs_dir=runs_dir)
        result.meta["run_id"] = run_dir.name
        result.meta["run_dir"] = str(run_dir)

    return result


def _representative(net_worth: np.ndarray, success: dict[str, np.ndarray],
                    k: int = DEFAULT_SAMPLE_PATHS) -> dict:
    """Pick a bounded, evenly-spaced mix of successful and failed paths."""
    overall = np.ones(net_worth.shape[0], dtype=bool)
    for v in success.values():
        overall &= v
    succ_idx = np.flatnonzero(overall)
    fail_idx = np.flatnonzero(~overall)

    def pick(idx: np.ndarray, n: int) -> np.ndarray:
        if len(idx) == 0 or n <= 0:
            return np.array([], dtype=int)
        return idx[np.linspace(0, len(idx) - 1, min(n, len(idx))).astype(int)]

    chosen = np.concatenate([pick(succ_idx, k // 2), pick(fail_idx, k - k // 2)]).astype(int)
    chosen = np.unique(chosen)
    return {
        "net_worth": net_worth[chosen],
        "success": overall[chosen],
        "index": chosen,
    }
