"""Persistence & reproducibility: save/load round-trip, checksum, cache management."""
from __future__ import annotations

import numpy as np

from fiscus_simulate.models import RunConfig
from fiscus_simulate.service import run_simulation
from fiscus_simulate.storage import (
    delete_details,
    delete_run,
    is_pinned,
    list_runs,
    load_run,
    new_run_id,
    pin,
    prune,
    save_run,
    summary_checksum,
)


def _cfg(n=200, sample=0):
    cfg = RunConfig.default().clone()
    cfg.simulation.n_scenarios = n
    cfg.simulation.chunk_size = n
    cfg.simulation.persist_sample_paths = sample
    return cfg


def test_save_load_round_trip(tmp_path):
    cfg = _cfg()
    res = run_simulation(cfg)
    d = save_run(res, cfg, runs_dir=tmp_path, run_id="run-a")
    assert (d / "config.yaml").exists()
    for f in ("summary", "percentiles", "failures", "scalars", "joint"):
        assert (d / f"{f}.parquet").exists()

    loaded = load_run("run-a", runs_dir=tmp_path)
    assert loaded.config == cfg
    assert loaded.metadata["n_scenarios"] == cfg.simulation.n_scenarios
    assert loaded.metadata["package_version"]
    assert "python_version" in loaded.metadata
    # percentile values survive the round trip
    p50 = res.summary.net_worth_pctiles_nominal[res.summary.percentiles.index(50)]
    assert np.allclose(loaded.percentiles["p50"].to_numpy(), p50)
    # joint (terminal-ranked) frame + mean metadata survive
    assert loaded.joint is not None
    assert list(loaded.joint["total_tax"]) == list(res.summary.joint_by_terminal["total_tax"])
    assert "scalar_means" in loaded.metadata
    assert loaded.metadata["scalar_means"]["total_tax"] == res.summary.scalar_means["total_tax"]


def test_joint_terminal_rows_are_monotone_in_terminal(tmp_path):
    """Terminal-ranked rows read across as real scenarios: terminal NW is non-decreasing."""
    res = run_simulation(_cfg())
    tn = res.summary.joint_by_terminal["terminal_nominal"]
    assert np.all(np.diff(tn) >= 0)


def test_checksum_reproducible(tmp_path):
    cfg = _cfg()
    a = run_simulation(cfg)
    b = run_simulation(cfg)  # same seed -> identical summary
    assert summary_checksum(a.summary) == summary_checksum(b.summary)
    save_run(a, cfg, runs_dir=tmp_path, run_id="run-c")
    loaded = load_run("run-c", runs_dir=tmp_path)
    assert loaded.metadata["summary_checksum"] == summary_checksum(b.summary)


def test_persist_via_run_simulation(tmp_path):
    cfg = _cfg()
    res = run_simulation(cfg, persist=True, runs_dir=tmp_path)
    assert "run_id" in res.meta
    assert (tmp_path / res.meta["run_id"] / "metadata.json").exists()


def test_optional_paths_and_delete_details(tmp_path):
    cfg = _cfg(sample=10)
    res = run_simulation(cfg)
    d = save_run(res, cfg, runs_dir=tmp_path, run_id="run-p")
    assert (d / "paths.parquet").exists()
    delete_details("run-p", runs_dir=tmp_path)
    assert not (d / "paths.parquet").exists()
    assert (d / "summary.parquet").exists()  # summary kept


def test_list_and_delete(tmp_path):
    cfg = _cfg()
    save_run(run_simulation(cfg), cfg, runs_dir=tmp_path, run_id="run-1")
    save_run(run_simulation(cfg), cfg, runs_dir=tmp_path, run_id="run-2")
    infos = list_runs(runs_dir=tmp_path)
    assert {i.run_id for i in infos} == {"run-1", "run-2"}
    assert all(0.0 <= i.overall_success_rate <= 1.0 for i in infos)
    delete_run("run-1", runs_dir=tmp_path)
    assert {i.run_id for i in list_runs(runs_dir=tmp_path)} == {"run-2"}


def test_pin_protects_from_prune(tmp_path):
    cfg = _cfg()
    save_run(run_simulation(cfg), cfg, runs_dir=tmp_path, run_id="keep")
    save_run(run_simulation(cfg), cfg, runs_dir=tmp_path, run_id="drop")
    pin("keep", runs_dir=tmp_path)
    assert is_pinned("keep", runs_dir=tmp_path)
    removed = prune(max_bytes=1, runs_dir=tmp_path)  # everything unpinned exceeds budget
    assert "drop" in removed
    assert {i.run_id for i in list_runs(runs_dir=tmp_path)} == {"keep"}


def test_prune_removes_incomplete(tmp_path):
    (tmp_path / "half-written").mkdir()  # no metadata.json -> incomplete
    removed = prune(runs_dir=tmp_path)
    assert "half-written" in removed
    assert not (tmp_path / "half-written").exists()


def test_new_run_id_shape():
    rid = new_run_id()
    assert rid.endswith(tuple("0123456789abcdef"))
    assert "Z-" in rid
