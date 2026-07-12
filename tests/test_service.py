"""Chunked execution, summaries, and the service seam."""
from __future__ import annotations

import numpy as np

from fiscus_simulate.analysis.summary import PCTS
from fiscus_simulate.models import RunConfig
from fiscus_simulate.returns.gbm import GBMReturns
from fiscus_simulate.service import make_generator, run_simulation


def _cfg(n=500, chunk=500):
    cfg = RunConfig.default().clone()
    cfg.simulation.n_scenarios = n
    cfg.simulation.chunk_size = chunk
    return cfg


def test_iter_chunks_matches_single_generate():
    cfg = RunConfig.default()
    gen = GBMReturns(cfg)
    whole = gen.generate(250).nominal_total
    chunks = list(gen.iter_chunks(250, 64))
    stitched = np.concatenate([c.nominal_total for c in chunks], axis=0)
    assert stitched.shape == whole.shape
    assert np.array_equal(stitched, whole)  # bit-identical


def test_chunked_equals_unchunked():
    one = run_simulation(_cfg(500, 500))
    many = run_simulation(_cfg(500, 137))
    assert one.summary.success_rates == many.summary.success_rates
    assert np.allclose(one.summary.net_worth_pctiles_nominal,
                       many.summary.net_worth_pctiles_nominal)
    assert np.allclose(one.summary.terminal_pctiles_nominal,
                       many.summary.terminal_pctiles_nominal)


def test_summary_invariants():
    res = run_simulation(_cfg(800, 200))
    sm = res.summary
    assert sm.n_scenarios == 800
    for rate in sm.success_rates.values():
        assert 0.0 <= rate <= 1.0
    assert 0.0 <= sm.overall_success_rate <= 1.0
    # percentile trajectories monotone across percentiles at each period
    assert np.all(np.diff(sm.net_worth_pctiles_nominal, axis=0) >= -1e-6)
    # every path either fails at some period or never fails
    assert int(sm.failure_timing.sum()) + sm.n_never_fail == 800
    # deflator matches constant inflation
    T = res.meta["n_scenarios"] and sm.deflator.shape[0]
    assert sm.deflator.shape[0] == 160 == T
    assert sm.deflator[0] > 1.0 and np.all(np.diff(sm.deflator) > 0)


def test_tail_refined_percentile_grid():
    # Symmetric, dense in the tails, monotone; spans p0.1 .. p99.9.
    assert PCTS[0] == 0.1 and PCTS[-1] == 99.9
    assert 50.0 in PCTS and 10.0 in PCTS and 90.0 in PCTS
    assert list(PCTS) == sorted(PCTS) and len(set(PCTS)) == len(PCTS)
    assert all(PCTS[i] < PCTS[i + 1] for i in range(len(PCTS) - 1))


def test_terminal_histogram_covers_all_scenarios():
    res = run_simulation(_cfg(600, 300))
    sm = res.summary
    assert sm.terminal_hist_edges.shape[0] == sm.terminal_hist_counts.shape[0] + 1
    assert int(sm.terminal_hist_counts.sum()) == 600  # every scenario binned (clipped)


def test_real_below_nominal_when_inflation_positive():
    res = run_simulation(_cfg(300, 300))
    sm = res.summary
    # Deflating shrinks magnitude (deflator >= 1) — real is closer to zero than nominal,
    # for either sign (net worth can be negative once a plan is funded by debt).
    assert np.all(np.abs(sm.net_worth_pctiles_real) <= np.abs(sm.net_worth_pctiles_nominal) + 1e-6)
    assert sm.terminal_pctiles_real[-1] < sm.terminal_pctiles_nominal[-1]  # positive top tail


def test_representative_paths_bounded():
    res = run_simulation(_cfg(500, 500))
    sp = res.sample_paths
    assert sp["net_worth"].shape[0] <= 20
    assert sp["net_worth"].shape[1] == 160
    assert sp["success"].shape[0] == sp["net_worth"].shape[0]


def test_meta_and_percentiles_present():
    res = run_simulation(_cfg(200, 200))
    assert res.meta["n_scenarios"] == 200
    assert res.meta["generator"] == "gbm"
    assert res.meta["runtime_s"] >= 0.0
    assert res.summary.percentiles == PCTS


def test_deterministic_generator_via_service():
    cfg = _cfg(50, 50)
    cfg.return_generator.kind = "deterministic"
    res = run_simulation(cfg, generator=make_generator(cfg))
    # identical scenarios -> a single distinct terminal value, rate is 0 or 1
    assert np.allclose(res.summary.net_worth_pctiles_nominal[0],
                       res.summary.net_worth_pctiles_nominal[-1])
    assert res.summary.overall_success_rate in (0.0, 1.0)
