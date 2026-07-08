"""Run directories, Parquet summaries, cache policy, and reproducibility metadata.

This is the persistence boundary — the one place pandas/pyarrow are used. A run's
compact outputs (summary, percentile trajectories, failure timing, scalar distributions,
optional sampled paths) are written under the app-state dir; the full scenario cube is
never persisted. Metadata captures enough to reproduce and verify a run.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .analysis.summary import SimulationSummary
from .config import load_config, save_config
from .models import RunConfig

_DEP_PACKAGES = ("numpy", "pandas", "pyarrow", "pydantic")
_PINNED_MARKER = "PINNED"


def default_runs_dir() -> Path:
    """App-state run directory (`$FISCUS_SIMULATE_HOME` or `~/.fiscus_simulate`)."""
    home = os.environ.get("FISCUS_SIMULATE_HOME")
    base = Path(home) if home else Path.home() / ".fiscus_simulate"
    return base / "simulation_runs"


def new_run_id(now: datetime | None = None) -> str:
    """Readable, sortable, collision-safe run id: ``YYYYMMDDTHHMMSSZ-<4hex>``."""
    now = now or datetime.now(UTC)
    return now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


# --------------------------------------------------------------------- dataclasses
@dataclass
class RunInfo:
    """Lightweight listing entry for a saved run."""

    run_id: str
    created: str
    n_scenarios: int
    overall_success_rate: float
    size_bytes: int
    pinned: bool


@dataclass
class LoadedRun:
    """A run read back from disk."""

    run_id: str
    metadata: dict
    config: RunConfig
    summary: pd.DataFrame
    percentiles: pd.DataFrame
    failures: pd.DataFrame
    scalars: pd.DataFrame
    joint: pd.DataFrame | None = None  # terminal-NW-ranked outcomes (None on legacy runs)


# ------------------------------------------------------------------ reproducibility
def _git_commit() -> str | None:
    """Best-effort git commit hash of the source checkout (``None`` off a checkout)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def _dep_versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for pkg in _DEP_PACKAGES:
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = None
    return out


def summary_checksum(summary: SimulationSummary) -> str:
    """Stable SHA-256 over the summary arrays — same code+config+seed reproduces it."""
    h = hashlib.sha256()
    for arr in (summary.net_worth_pctiles_nominal, summary.failure_timing,
                summary.deflator, summary.terminal_pctiles_nominal):
        h.update(np.ascontiguousarray(arr, dtype=np.float64).tobytes())
    h.update(json.dumps(summary.success_rates, sort_keys=True).encode())
    h.update(json.dumps(summary.terminal_stats, sort_keys=True).encode())
    return h.hexdigest()


# ------------------------------------------------------------------ dataframe views
def _percentiles_frame(sm: SimulationSummary) -> pd.DataFrame:
    cols = {f"p{p}": sm.net_worth_pctiles_nominal[i] for i, p in enumerate(sm.percentiles)}
    df = pd.DataFrame(cols)
    df.insert(0, "period", np.arange(len(df)))
    df["deflator"] = sm.deflator
    return df


def _failures_frame(sm: SimulationSummary) -> pd.DataFrame:
    return pd.DataFrame({"period": np.arange(len(sm.failure_timing)),
                         "first_failure_count": sm.failure_timing})


def _scalars_frame(sm: SimulationSummary) -> pd.DataFrame:
    """Marginal per-column percentiles (each metric sorted independently)."""
    data = {"percentile": list(sm.percentiles),
            "terminal_nominal": sm.terminal_pctiles_nominal,
            "terminal_real": sm.terminal_pctiles_real}
    data.update({k: v for k, v in sm.scalar_pctiles.items() if k != "terminal_nominal"})
    return pd.DataFrame(data)


def _joint_frame(sm: SimulationSummary) -> pd.DataFrame:
    """Joint outcomes at each terminal-net-worth rank (a row is one real scenario)."""
    data = {"percentile": list(sm.percentiles)}
    data.update(sm.joint_by_terminal)
    return pd.DataFrame(data)


def _summary_frame(sm: SimulationSummary) -> pd.DataFrame:
    rows: list[tuple[str, float]] = []
    for k, v in sm.success_rates.items():
        rows.append((f"success_rate.{k}", float(v)))
    rows.append(("overall_success_rate", float(sm.overall_success_rate)))
    for k, v in sm.terminal_stats.items():
        rows.append((f"terminal.{k}", float(v)))
    rows.append(("n_scenarios", float(sm.n_scenarios)))
    rows.append(("n_never_fail", float(sm.n_never_fail)))
    return pd.DataFrame(rows, columns=["metric", "value"])


def _paths_frame(sample: dict) -> pd.DataFrame:
    nw = sample["net_worth"]
    k, T = nw.shape
    idx = sample["index"]
    succ = sample["success"]
    recs = [(int(idx[i]), bool(succ[i]), t, float(nw[i, t]))
            for i in range(k) for t in range(T)]
    return pd.DataFrame(recs, columns=["path_index", "success", "period", "net_worth"])


# ---------------------------------------------------------------------------- save
def save_run(result, config: RunConfig, runs_dir: Path | None = None,
             run_id: str | None = None, status: str = "complete",
             warnings: list[str] | None = None) -> Path:
    """Persist a :class:`SimulationResult` to ``runs_dir/<run_id>/`` and return the path.

    Parameters
    ----------
    result : SimulationResult
        From :func:`fiscus_simulate.service.run_simulation`.
    config : RunConfig
        The exact run configuration (persisted as YAML).
    runs_dir : Path, optional
        Parent directory (defaults to :func:`default_runs_dir`).
    """
    runs_dir = runs_dir or default_runs_dir()
    run_id = run_id or new_run_id()
    d = Path(runs_dir) / run_id
    d.mkdir(parents=True, exist_ok=True)

    sm = result.summary
    save_config(config, d / "config.yaml")
    _summary_frame(sm).to_parquet(d / "summary.parquet", index=False)
    _percentiles_frame(sm).to_parquet(d / "percentiles.parquet", index=False)
    _failures_frame(sm).to_parquet(d / "failures.parquet", index=False)
    _scalars_frame(sm).to_parquet(d / "scalars.parquet", index=False)
    _joint_frame(sm).to_parquet(d / "joint.parquet", index=False)
    if config.simulation.persist_sample_paths > 0:
        _paths_frame(result.sample_paths).to_parquet(d / "paths.parquet", index=False)

    metadata = {
        "run_id": run_id,
        "created": datetime.now(UTC).isoformat(),
        "seed": int(config.simulation.seed),
        "generator": config.return_generator.kind,
        "package_version": __version__,
        "git_commit": _git_commit(),
        "python_version": platform.python_version(),
        "dependencies": _dep_versions(),
        "n_scenarios": int(sm.n_scenarios),
        "horizon_years": int(config.household.horizon_years),
        "runtime_s": float(result.meta.get("runtime_s", 0.0)),
        "status": status,
        "warnings": warnings or [],
        "overall_success_rate": float(sm.overall_success_rate),
        "scalar_means": {k: float(v) for k, v in sm.scalar_means.items()},
        "summary_checksum": summary_checksum(sm),
    }
    (d / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return d


# ---------------------------------------------------------------------------- load
def load_run(run_id: str, runs_dir: Path | None = None) -> LoadedRun:
    """Read a saved run's metadata, config, and summary tables."""
    d = (Path(runs_dir) if runs_dir else default_runs_dir()) / run_id
    if not (d / "metadata.json").exists():
        raise FileNotFoundError(f"no run {run_id!r} in {d.parent}")
    metadata = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    joint_path = d / "joint.parquet"
    return LoadedRun(
        run_id=run_id,
        metadata=metadata,
        config=load_config(d / "config.yaml"),
        summary=pd.read_parquet(d / "summary.parquet"),
        percentiles=pd.read_parquet(d / "percentiles.parquet"),
        failures=pd.read_parquet(d / "failures.parquet"),
        scalars=pd.read_parquet(d / "scalars.parquet"),
        joint=pd.read_parquet(joint_path) if joint_path.exists() else None,
    )


# ---------------------------------------------------------------------- cache mgmt
def _dir_size(d: Path) -> int:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())


def list_runs(runs_dir: Path | None = None) -> list[RunInfo]:
    """List saved runs, newest first."""
    base = Path(runs_dir) if runs_dir else default_runs_dir()
    if not base.exists():
        return []
    infos: list[RunInfo] = []
    for d in base.iterdir():
        meta_path = d / "metadata.json"
        if not meta_path.is_file():
            continue
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        infos.append(RunInfo(
            run_id=m.get("run_id", d.name),
            created=m.get("created", ""),
            n_scenarios=int(m.get("n_scenarios", 0)),
            overall_success_rate=float(m.get("overall_success_rate", 0.0)),
            size_bytes=_dir_size(d),
            pinned=(d / _PINNED_MARKER).exists(),
        ))
    infos.sort(key=lambda r: r.created, reverse=True)
    return infos


def is_pinned(run_id: str, runs_dir: Path | None = None) -> bool:
    d = (Path(runs_dir) if runs_dir else default_runs_dir()) / run_id
    return (d / _PINNED_MARKER).exists()


def pin(run_id: str, on: bool = True, runs_dir: Path | None = None) -> None:
    """Protect (or unprotect) a run from automatic pruning."""
    d = (Path(runs_dir) if runs_dir else default_runs_dir()) / run_id
    marker = d / _PINNED_MARKER
    if on:
        marker.touch()
    elif marker.exists():
        marker.unlink()


def delete_run(run_id: str, runs_dir: Path | None = None) -> None:
    """Delete a run directory entirely."""
    d = (Path(runs_dir) if runs_dir else default_runs_dir()) / run_id
    if d.exists():
        shutil.rmtree(d)


def delete_details(run_id: str, runs_dir: Path | None = None) -> None:
    """Drop the optional per-path sample, keeping the summary tables."""
    d = (Path(runs_dir) if runs_dir else default_runs_dir()) / run_id
    paths = d / "paths.parquet"
    if paths.exists():
        paths.unlink()


def prune(max_age_seconds: float | None = None, max_bytes: int | None = None,
          runs_dir: Path | None = None) -> list[str]:
    """Remove old / oversized / incomplete unpinned runs. Never touches pinned runs.

    Returns the run ids removed (the caller logs them — no silent truncation).
    """
    base = Path(runs_dir) if runs_dir else default_runs_dir()
    if not base.exists():
        return []
    removed: list[str] = []
    now = datetime.now(UTC)

    entries = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        pinned = (d / _PINNED_MARKER).exists()
        if not meta_path.is_file():
            if not pinned:  # incomplete/temp run
                shutil.rmtree(d)
                removed.append(d.name)
            continue
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        entries.append((d, m, pinned))

    # Age limit
    if max_age_seconds is not None:
        for d, m, pinned in entries:
            if pinned:
                continue
            created = datetime.fromisoformat(m["created"])
            if (now - created).total_seconds() > max_age_seconds:
                shutil.rmtree(d)
                removed.append(d.name)
    entries = [(d, m, p) for d, m, p in entries if d.exists()]

    # Size limit: drop oldest unpinned until under budget
    if max_bytes is not None:
        entries.sort(key=lambda e: e[1].get("created", ""))  # oldest first
        total = sum(_dir_size(d) for d, _, _ in entries)
        for d, m, pinned in entries:
            if total <= max_bytes:
                break
            if pinned:
                continue
            total -= _dir_size(d)
            shutil.rmtree(d)
            removed.append(d.name)
    return removed
