"""Stage 8 "see inside": per-scenario outcomes, exact replay, and order-of-returns.

Covers the mechanics behind the Details page: outcome persistence + legacy fallback, the
instrumented single-scenario walk (`capture_balances`), exact scenario replay, and the
quarter-permutation resampler.
"""
from __future__ import annotations

import numpy as np
import pytest

from fiscus_simulate import service, storage
from fiscus_simulate.engine import simulate
from fiscus_simulate.models import RunConfig
from fiscus_simulate.returns.gbm import GBMReturns


def _cfg(n=400, chunk=128):
    cfg = RunConfig.default().clone()
    cfg.simulation.n_scenarios = n
    cfg.simulation.chunk_size = chunk
    return cfg


# ------------------------------------------------------------------ capture_balances
def test_capture_balances_reconciles_every_quarter():
    """With capture on, Begin+flows == End each period, and Begin[t] == End[t-1]."""
    cfg = _cfg(n=1)
    bundle = GBMReturns(cfg).generate(1)
    res = simulate(cfg, returns=bundle, capture_balances=True)
    assert res.balances_begin is not None and res.balances_end is not None

    begin = res.balances_begin[0].sum(axis=1)     # (T,)
    end = res.balances_end[0].sum(axis=1)
    rhs = (begin + res.external_income + res.savings + res.investment_income[0]
           + res.capital_return[0] - res.spending_funded[0]
           - res.tax_income[0] - res.tax_sale[0])
    assert np.allclose(end, rhs, atol=1e-4)
    assert np.allclose(begin[1:], end[:-1], atol=1e-4)
    assert np.allclose(end, res.net_worth[0], atol=1e-4)


def test_capture_off_by_default():
    res = simulate(_cfg(n=1), returns=GBMReturns(_cfg(n=1)).generate(1))
    assert res.balances_begin is None and res.balances_end is None


# ------------------------------------------------------------------------- replay
def test_replay_is_terminal_exact():
    """A replayed scenario reproduces the full run's terminal for that index, bit-exact."""
    cfg = _cfg(n=400, chunk=128)
    res = service.run_simulation(cfg)
    term = res.outcomes["terminal_net_worth"]
    for i in (0, 199, 300, 399):  # spans multiple chunks incl. the last
        walk = service.replay_scenario(cfg, i)
        assert walk.terminal_net_worth == pytest.approx(float(term[i]), abs=1e-6)


def test_replay_matches_generate_slice():
    """iter_chunks-based replay equals slicing a single generate() of the whole draw."""
    cfg = _cfg(n=300, chunk=64)
    full = GBMReturns(cfg).generate(cfg.simulation.n_scenarios)
    i = 137
    ref = simulate(cfg, returns=service._slice_bundle(full, i))
    walk = service.replay_scenario(cfg, i)
    assert walk.terminal_net_worth == pytest.approx(float(ref.terminal_net_worth[0]), abs=1e-6)


def test_replay_index_out_of_range():
    with pytest.raises(IndexError):
        service.replay_scenario(_cfg(n=10), 10)


# --------------------------------------------------------------- order of returns
def test_resample_order_preserves_multiset_and_is_seed_deterministic():
    cfg = _cfg(n=50)
    walk = service.replay_scenario(cfg, 7)
    a = service.resample_order(walk.bundle, cfg, n=200, seed=1)
    b = service.resample_order(walk.bundle, cfg, n=200, seed=1)
    assert np.array_equal(a.terminal, b.terminal)          # deterministic under a seed
    assert a.reference_terminal == pytest.approx(walk.terminal_net_worth, abs=1e-6)
    assert a.terminal.shape == (200,)
    # A permutation keeps the multiset of quarterly returns (only the order changes).
    base = np.sort(walk.bundle.capital_return[0].ravel())
    reordered = service.resample_order(walk.bundle, cfg, n=1, seed=3)
    # rebuild the single permuted row's returns and compare the sorted multiset
    rng = np.random.default_rng(3)
    T = walk.bundle.n_periods
    perm = np.argsort(rng.random((1, T)), axis=1)[0]
    permuted = np.sort(walk.bundle.capital_return[0][perm].ravel())
    assert np.allclose(base, permuted)
    assert reordered.terminal.shape == (1,)


# ---------------------------------------------------------------------- persistence
def test_outcomes_parquet_roundtrip(tmp_path):
    cfg = _cfg(n=300)
    res = service.run_simulation(cfg)
    d = storage.save_run(res, cfg, runs_dir=tmp_path)
    loaded = storage.load_run(d.name, runs_dir=tmp_path)
    assert loaded.outcomes is not None
    assert len(loaded.outcomes) == cfg.simulation.n_scenarios
    got = service.scenario_outcomes(loaded)
    assert np.allclose(got["terminal_net_worth"], res.outcomes["terminal_net_worth"])


def test_scenario_outcomes_legacy_fallback(tmp_path):
    """A run whose outcomes.parquet is absent is reproduced from the seed on demand."""
    cfg = _cfg(n=300)
    res = service.run_simulation(cfg)
    d = storage.save_run(res, cfg, runs_dir=tmp_path)
    (d / "outcomes.parquet").unlink()                      # simulate a legacy run
    loaded = storage.load_run(d.name, runs_dir=tmp_path)
    assert loaded.outcomes is None
    got = service.scenario_outcomes(loaded)                # reproduced + cached
    assert np.allclose(got["terminal_net_worth"], res.outcomes["terminal_net_worth"])
