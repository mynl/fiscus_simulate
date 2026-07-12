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
from .assets import BONDS, CASH, STOCKS
from .engine import simulate
from .models import RunConfig
from .returns.base import ReturnGenerator, ReturnsBundle
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
    outcomes: dict              # per-scenario (S,) vectors: terminal/failure/min/tax


@dataclass
class ScenarioWalk:
    """One reproduced scenario's quarter-by-quarter walk (from a single-scenario replay)."""

    index: int
    net_worth: np.ndarray                  # (T,) end-of-period net worth, for the overlay
    terminal_net_worth: float
    first_failure_period: int              # -1 if never failed
    columns: dict[str, np.ndarray]         # per-period (T,) walk arrays, keyed by column
    bundle: ReturnsBundle                  # the 1-scenario returns, reused by the Order tab


@dataclass
class OrderResult:
    """Order-of-returns experiment: terminal wealth under many quarter-permutations."""

    terminal: np.ndarray                   # (n,) terminal net worth per reordering
    first_failure_period: np.ndarray       # (n,) -1 where never failed
    reference_terminal: float              # the actual scenario's terminal (unpermuted)
    n: int
    seed: int | None


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
    outcomes = {
        "terminal_net_worth": terminal,
        "first_failure_period": first_fail,
        "min_net_worth": min_nw,
        "total_tax": total_tax,
    }
    meta = {
        "n_scenarios": S,
        "seed": config.simulation.seed,
        "generator": config.return_generator.kind,
        "chunk_size": chunk,
        "runtime_s": runtime,
    }
    result = SimulationResult(summary=summary, sample_paths=sample, meta=meta,
                             outcomes=outcomes)

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


# --------------------------------------------------------- "see inside" a scenario
# Reproduced-outcomes cache for legacy runs that predate outcomes.parquet, keyed by run id.
_OUTCOMES_CACHE: dict[str, dict[str, np.ndarray]] = {}
_OUTCOME_KEYS = ("terminal_net_worth", "first_failure_period", "min_net_worth", "total_tax")


def scenario_outcomes(loaded) -> dict[str, np.ndarray]:
    """Per-scenario outcome vectors for a loaded run (for percentile→scenario lookup).

    Returns a dict of ``(S,)`` arrays keyed by :data:`_OUTCOME_KEYS`. New runs read the
    persisted ``outcomes.parquet``; legacy runs without it are reproduced once from the
    stored seed + config and cached in-memory (identical by construction — same code,
    config and seed).

    Parameters
    ----------
    loaded : storage.LoadedRun
        The run to read outcomes for.
    """
    if loaded.outcomes is not None:
        return {k: loaded.outcomes[k].to_numpy() for k in _OUTCOME_KEYS}
    cached = _OUTCOMES_CACHE.get(loaded.run_id)
    if cached is None:
        cached = run_simulation(loaded.config).outcomes
        _OUTCOMES_CACHE[loaded.run_id] = cached
    return cached


def _slice_bundle(bundle: ReturnsBundle, row: int) -> ReturnsBundle:
    """A single-scenario ``ReturnsBundle`` from row ``row`` (broadcast rows tolerated)."""
    r = 0 if bundle.capital_return.shape[0] == 1 else row
    return ReturnsBundle(
        capital_return=np.array(bundle.capital_return[r:r + 1]),
        income_yield=np.array(bundle.income_yield[r:r + 1]),
        nominal_total=np.array(bundle.nominal_total[r:r + 1]),
        overall_inflation_q=bundle.overall_inflation_q,
    )


def replay_scenario(config: RunConfig, index: int,
                    generator: ReturnGenerator | None = None) -> ScenarioWalk:
    """Reproduce one scenario exactly and capture its quarter-by-quarter walk.

    Parameters
    ----------
    config : RunConfig
        The run configuration (single source of truth; seed lives here).
    index : int
        The scenario's position in the ``0..S-1`` cube (as ranked/listed by the caller).
    generator : ReturnGenerator, optional
        Override the generator (defaults to :func:`make_generator`).

    Notes
    -----
    The RNG is one sequential draw (not ``seed+i``), so regenerating scenario ``index``
    means streaming return chunks up to the one containing it and slicing that single row
    — exact, at a cost that scales with ``index``. The engine then runs for that lone
    scenario with ``capture_balances=True``; the reconciliation identity holds every
    quarter: ``End = Begin + ext_income + invest_income + savings + capital − spend − tax``.
    """
    gen = generator or make_generator(config)
    S = config.simulation.n_scenarios
    if not 0 <= index < S:
        raise IndexError(f"scenario index {index} out of range 0..{S - 1}")
    chunk = config.simulation.chunk_size

    target = None
    seen = 0
    for bundle in gen.iter_chunks(S, chunk):
        c = bundle.n_scenarios
        if seen <= index < seen + c:
            target = _slice_bundle(bundle, index - seen)
            break
        seen += c
    if target is None:  # pragma: no cover - guards an under-filling generator
        raise RuntimeError(f"generator did not yield scenario {index}")

    res = simulate(config, returns=target, capture_balances=True)
    begin = res.balances_begin[0]          # (T, n_asset), beginning-of-period by asset
    realized = res.realized_gain[0]
    columns = {
        "begin": begin.sum(axis=1),
        "stocks": begin[:, STOCKS],        # beginning composition (ending = next begin)
        "bonds": begin[:, BONDS],
        "cash": begin[:, CASH],
        "ext_income": res.external_income,
        "invest_income": res.investment_income[0],
        "savings": res.savings,
        "spending": res.spending_funded[0],
        "tax": res.tax_income[0] + res.tax_sale[0],
        "realized": realized,
        # Of the period's capital return, the part crystallized by sales is "realized";
        # the remainder is the change in unrealized gains (reconciles exactly).
        "unrealized": res.capital_return[0] - realized,
        "end": res.net_worth[0],
    }
    return ScenarioWalk(
        index=index,
        net_worth=res.net_worth[0],
        terminal_net_worth=float(res.terminal_net_worth[0]),
        first_failure_period=int(res.first_failure_period[0]),
        columns=columns,
        bundle=target,
    )


def resample_order(bundle: ReturnsBundle, config: RunConfig, n: int = 1000,
                   seed: int | None = None) -> OrderResult:
    """Order-of-returns experiment: rerun the drawdown under ``n`` quarter-permutations.

    Parameters
    ----------
    bundle : ReturnsBundle
        A single-scenario bundle (from :func:`replay_scenario`).
    config : RunConfig
        The run configuration.
    n : int
        Number of reorderings to draw.
    seed : int, optional
        Seed for the permutation RNG (``None`` → nondeterministic; a "throwaway" analysis).

    Notes
    -----
    Each reordering permutes the 160-quarter time axis (no replacement) *identically*
    across assets, so within-quarter cross-asset correlation is preserved and only the
    *order* of returns changes — isolating sequence-of-returns risk from the return
    environment. Income yield is constant across quarters, so reordering leaves it
    unchanged. Not persisted.
    """
    cap = bundle.capital_return[0]          # (T, n_asset)
    nom = bundle.nominal_total[0]
    yld = bundle.income_yield[0]
    T = cap.shape[0]
    rng = np.random.default_rng(seed)
    perms = np.argsort(rng.random((n, T)), axis=1)   # (n, T), each row a permutation
    reordered = ReturnsBundle(
        capital_return=cap[perms],                    # (n, T, n_asset)
        income_yield=np.broadcast_to(yld, (n, T, yld.shape[-1])).copy(),
        nominal_total=nom[perms],
        overall_inflation_q=bundle.overall_inflation_q,
    )
    res = simulate(config, returns=reordered)
    # Reference: the unpermuted scenario's own terminal.
    ref = simulate(config, returns=bundle).terminal_net_worth[0]
    return OrderResult(
        terminal=res.terminal_net_worth,
        first_failure_period=res.first_failure_period,
        reference_terminal=float(ref),
        n=n,
        seed=seed,
    )
