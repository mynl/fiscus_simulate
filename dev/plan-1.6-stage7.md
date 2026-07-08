# Plan 1.6 — Stage 7: Results dashboard & charts

**Goal:** turn a persisted run into an explorable results view — the net-worth **funnel**,
terminal-wealth and failure-timing distributions, representative paths, and a two-run
**comparison** — plus the **tail-refined percentile grid**. Charts use **uPlot** (same as
`fiscus_project`). **Version 1.6.0.**

**In scope:** uPlot wiring; funnel; terminal-wealth dist; failure-timing; representative
paths; run comparison; tail-refined `PCTS`; csv-grid numeric tables; results-forward
dashboard. **Out of scope:** sequence-risk prototype (Stage 8); mortality-weighting
(V2, see `dev/TODO.md`). **Assumes** pre-retirement accumulation (1.5.4) has landed, so
the funnel shows the accumulation ramp before the drawdown.

## 1. Charting stack — uPlot (mirror `fiscus_project`)

- Load uPlot in `base.html` from CDN, matching the sibling exactly:
  `uplot@1.6.30` (`uPlot.min.css` + `uPlot.iife.min.js`). *Option:* vendor the two files
  under `web/static/vendor/uplot/` for offline/VPS robustness — recommend vendoring
  (localhost tool, no egress ethos) but CDN is the zero-effort match. **Confirm.**
- Pattern (from `fiscus_project/web/views.py`): the **server builds the arrays**
  (`x`, one array per series) and JSON-dumps them into a small inline `<script>` that
  calls `new uPlot(opts, data, host)`. A `series.value` formatter drives the hover
  readout. Add a `web/charts.py` helper (`uplot_block(div_id, x, serieses, opts)`) so
  routes stay thin and the pattern isn't copy-pasted. Charts are **presentation only** —
  fed from the persisted Parquet summaries, never the engine.

## 2. Tail-refined percentile grid (prerequisite)

Replace the 9-point `PCTS` with a **symmetric, tail-dense** grid (author, 2026-07-08):

```
0.001 → 0.01 step 0.001    (p0.1 … p1)
0.01  → 0.1  step 0.01     (p1  … p10)
0.1   → 0.9  step 0.1      (p10 … p90)
0.9   → 0.99 step 0.01     (p90 … p99)
0.99  → 0.999 step 0.001   (p99 … p99.9)
```

(as fractions; ×100 for `np.percentile`). Deduplicate the shared endpoints. Ripples —
all mechanical but touch several files:
- `analysis/summary.py`: `PCTS` becomes floats; percentile arrays lengthen.
- `storage.py`: **the `p{int}` column-naming scheme breaks** (0.1, 99.9 aren't ints).
  Switch `percentiles.parquet` / `scalars` / `joint` to a **tidy long form**
  (`percentile` value column) or a float-safe name (`p00_100` … `p99_900`). Prefer tidy
  long — it's what csv-grid and uPlot both want and kills the naming problem.
- `summary_checksum`: recomputes (values change) — expected; update the reproducibility
  note, not a regression.
- Distribution table + glossary: relabel; the table gets more rows (dense tails).
- Tests: percentile-index lookups (`.index(50)` → find the p=50 row) and any `p50`
  column reads.

Do this **first** in the stage; the funnel and tables consume it.

## 3. The charts

Each is fed by an existing Parquet summary (no re-run), real/nominal via the stored
`deflator`.

- **Net-worth funnel** (headline). Percentile bands over the 160 quarters from
  `percentiles.parquet`: shaded p10–p90 and p25–p75 envelopes + median line, x = date
  axis (accumulation ramp then drawdown). **Real/nominal toggle** divides by `deflator`.
  Hover shows quarter + band values. Optional: overlay a couple of representative paths.
- **Terminal-wealth distribution.** From the (now dense) terminal percentiles — plot the
  **CDF / quantile curve** (robust, no binning choices) with the failure mass at ≤0
  called out; nominal/real toggle.
- **Failure timing.** Bar/line of `failures.parquet` (first-failure count by period) +
  cumulative failure curve — *when* plans break. (This is the seam the V2 mortality
  weighting reweights — note it in the glossary.)
- **Representative paths.** A handful of success + failure net-worth trajectories from
  `paths.parquet` (needs `persist_sample_paths > 0`; surface a note when absent).
- **Run comparison.** Pick two runs; overlay their funnels (median + p10/p90) and a
  side-by-side headline/distribution table. Drives the scenario-thinking goal.

## 4. csv-grid numeric tables

Keep the transposed outcome distribution (now tail-dense) as the numeric companion to the
funnel; add a percentile table behind each chart (the exact numbers the picture shows).
csv-grid handles the row count.

## 5. Dashboard & run view

- Run view (`run_detail.html`): funnel first, then distributions, then the numeric
  tables, reproducibility last (as now). Every computed panel keeps its **glossary**
  (the rule) — extend it to explain the bands, CDF, and failure-timing.
- Dashboard: recent-runs list links straight to the funnel; add "Compare" affordance.

## 6. Tests

- `PCTS` grid: monotone, symmetric, expected length, endpoints deduped.
- Storage round-trips the new percentile schema; `p=50` still recoverable.
- Chart data builders (`web/charts.py`) return well-formed arrays (lengths match x;
  real = nominal ÷ deflator); funnel bands ordered (p10 ≤ p50 ≤ p90 each period).
- Routes: funnel/terminal/failure blocks render (200, contain the `uPlot` init);
  comparison view with two runs; representative-paths absent → graceful note.
- All against a temp state dir; small runs.

## 7. Decisions (confirm before building)

1. **uPlot: vendor locally vs. CDN** (recommend vendor for offline; CDN matches sibling).
2. **Percentile Parquet schema: tidy long form** (recommend) vs. float-safe wide names.
3. **Terminal-wealth as CDF/quantile curve** (recommend, binning-free) vs. histogram.
4. Comparison in this stage vs. deferred — recommend a **minimal** two-run overlay now.
