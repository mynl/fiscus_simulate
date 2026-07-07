"""Opt-in performance benchmark: 100,000 paths x 160 quarters.

Not part of the routine test suite (see CLAUDE.md). Run manually:

    uv run python scripts/benchmark.py [n_scenarios] [chunk_size]

Prints runtime, the retained ``net_worth`` footprint, and headline results.
"""
from __future__ import annotations

import sys
from time import perf_counter

import numpy as np

from fiscus_simulate.models import RunConfig
from fiscus_simulate.service import run_simulation


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    chunk = int(sys.argv[2]) if len(sys.argv) > 2 else 10_000

    cfg = RunConfig.default().clone()
    cfg.simulation.n_scenarios = n
    cfg.simulation.chunk_size = chunk
    T = cfg.household.n_periods

    t0 = perf_counter()
    res = run_simulation(cfg)
    dt = perf_counter() - t0

    nw_mb = n * T * 8 / 1e6
    sm = res.summary
    print(f"{n:,} paths x {T} quarters, chunk {chunk:,}")
    print(f"  runtime            {dt:6.2f} s   ({n / dt:,.0f} paths/s)")
    print(f"  net_worth retained {nw_mb:6.0f} MB (the one full-size array)")
    print(f"  overall success    {100 * sm.overall_success_rate:5.1f} %")
    print(f"  terminal median    GBP {np.round(sm.terminal_pctiles_nominal[4]):,.0f} (nominal)")
    print(f"  terminal p10/p90   GBP {np.round(sm.terminal_pctiles_nominal[2]):,.0f}"
          f" / {np.round(sm.terminal_pctiles_nominal[6]):,.0f}")


if __name__ == "__main__":
    main()
