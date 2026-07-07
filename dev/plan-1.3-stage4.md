# Plan 1.3 — Stage 4: Vectorized execution & result summaries

**Goal:** run up to ~100k scenarios without holding the full cube, and reduce them to
compact summaries: success rates, failure timing, percentile trajectories (the funnel),
terminal/scalar distributions, and a bounded set of representative paths. **Version 1.3.0.**

**In scope:** chunked execution over the scenario axis; `analysis/summary.py`;
`service.py` orchestration seam; representative-path sampling; a perf check.
**Out of scope:** persistence to Parquet/run dirs (Stage 5), web/charts (6/7).

## 1. Chunking (memory discipline)

The engine is already vectorized over scenarios; Stage 4 adds **chunked generation +
streaming aggregation** so the full return cube never lives in memory at once.

- Generator gains `iter_chunks(n_scenarios, chunk_size)` yielding `ReturnsBundle`s that
  concatenate to a single `generate(n_scenarios)` — GBM streams from **one** RNG so
  chunking is bit-identical to one big draw (sequential `standard_normal` fills match).
- `service.run_simulation(config)` loops chunks, runs the engine per chunk, and fills
  preallocated outputs by offset.
- **Memory:** the one full-size array we retain is **`net_worth (S, T)`** (~128 MB at
  100k) — needed for *exact* percentile trajectories. Everything else is per-chunk and
  discarded: the GBM cube `(chunk, T, 3)` and the engine's per-chunk `(chunk, T)` fields.
  Peak ≈ `net_worth` + one chunk (~300 MB at 100k / chunk 10k). This is the pragmatic
  choice over a streaming-quantile approximation (t-digest) — exact and simple; revisit
  only if 128 MB ever bites. Per-scenario **scalars** (terminal, min, years-funded,
  first-failure, totals, success flags) are all `(S,)` — a few MB — kept for all paths.

## 2. Summaries (`analysis/summary.py`)

`summarize(net_worth, scalars, overall_inflation_q, config) -> SimulationSummary`:

- **Success rates** per criterion (1–4) + overall (all criteria).
- **Failure timing**: counts of first-failure by period (+ a "never" bucket).
- **Percentile trajectories**: `np.percentile(net_worth, PCTS, axis=0)` → `(n_pct, T)`
  nominal, with `PCTS = [1,5,10,25,50,75,90,95,99]`. Stored **nominal**; a `deflator`
  `(T,)` (`(1+pi_q)**(t+1)`) is stored so charts toggle real/nominal without recompute.
- **Terminal wealth**: mean/std/min/max + percentiles (nominal & real).
- **Scalar distributions**: percentiles of min-net-worth, years-funded, total tax,
  total sales.
- **Representative paths**: a bounded sample (e.g. 10 success + 10 fail) of full
  `net_worth` rows, chosen at summary time from the success mask.

`SimulationSummary` holds NumPy arrays (+ a `to_dict()` for Stage 5 persistence). No
pandas in the hot path; pandas/Parquet enters only at Stage 5's persistence boundary.

## 3. Service seam (`service.py`)

`run_simulation(config, generator=None) -> SimulationResult` with `SimulationResult =
{summary, sample_paths, meta}` where `meta` carries n_scenarios, seed, generator kind,
runtime seconds (timing/diagnostics per the ask). Default generator: GBM for
`return_generator.kind == "gbm"`. This is the single entry point the web layer (Stage 6)
will call — engine stays Flask-free.

## 4. Tests (Stage 4 acceptance)

- `iter_chunks` concatenation is bit-identical to one `generate(n)` (GBM).
- Chunked service run == unchunked (same seed, chunk_size 1 vs n vs a middle value):
  identical success rates and percentile trajectories.
- Summary shapes and invariants: rates in [0,1]; percentile monotone across PCTS;
  deflator matches inflation; representative sample sizes bounded.
- Small end-to-end `run_simulation` at a few thousand paths; assert plausible outputs.
- **Perf:** not a routine test. A `scripts/benchmark.py` runs 100k × 160 and prints
  runtime + peak memory for manual, opt-in use (per CLAUDE.md).

## 5. Decision (proceeding unless you object)

- **Hold `net_worth (S,T)` for exact funnel percentiles** (≈128 MB at 100k), chunk
  everything else. Simple and exact; the streaming-quantile alternative is a V2 nicety.
