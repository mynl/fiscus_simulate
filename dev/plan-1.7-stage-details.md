# Plan 1.7.0 — "See inside the simulations": Details + Order pages

Status: **implemented** (awaiting author sign-off before moving to `dev/done/`).

## Goal

Open the black box. From the Runs list, **Details** lets the author pick a percentile of
terminal net worth, choose one of the actual scenarios sitting there, and inspect it: its
quarter-by-quarter walk, its path overlaid on the funnel, and a throwaway order-of-returns
experiment that reshuffles that scenario's own returns to isolate sequence risk from the
return environment.

Ships as **1.7.0** (a full stage). The Order tab is a deliberate throwaway preview of the
sequence-risk prototype — `ReturnsBundle` was built to "hold returns fixed and permute the
time axis," which is exactly this.

## Two facts that shaped the design

1. Runs are exactly reproducible (seed in `metadata.json` + `config.yaml`), but scenario
   identity was discarded (`summary.py:133` computes `idx = order[ranks]` then drops it).
   → persist per-scenario outcomes.
2. The RNG is one sequential global draw, not `seed+i` (`gbm.py:72`). Reproducing scenario
   *i* streams draws `0…i` (chunked, exact). Cost scales with *i* (~1–2 s worst case) — fine
   for an interactive peek.

Author decisions: Order tab **permutes all 160 quarters** (no replacement); per-scenario
outcomes **persisted** at run time.

## What was built

- **Persistence** — `outcomes.parquet` (`scenario, terminal_net_worth,
  first_failure_period, min_net_worth, total_tax`), written from vectors `service.py`
  already had; `LoadedRun.outcomes`; `service.scenario_outcomes` with reproduce-on-demand
  fallback for legacy runs.
- **Engine** — opt-in `simulate(..., capture_balances=True)` records consolidated per-asset
  `balances_begin/end` `(S,T,n_asset)`; off by default (hot path untouched). One engine, no
  order-of-operations duplication.
- **Service** — `replay_scenario` (chunked exact replay → `ScenarioWalk`); `resample_order`
  (n quarter-permutations, vectorized single engine run → `OrderResult`).
- **Web** — `/runs/<id>/details` route; `_funnel_block(..., overlay=)`; walk-frame + order
  histogram/stats helpers; `run_details.html` (pickers, overlay funnel, Bootstrap tabs
  Consolidated | By account [placeholder] | Order, glossary); Summary/Details buttons on
  the Runs list.

## Verification

`uv run --no-sync pytest -q` → 89 green; `ruff check` clean. Smoke: replay is
terminal-exact across chunks; the walk reconciles every quarter; the order resample is
seed-deterministic with a matching reference terminal; `outcomes.parquet` round-trips and
the legacy fallback reproduces it. Author to smoke the app: Runs → Details → pick p50 →
pick a scenario → confirm the pink overlay tracks the funnel, the Consolidated grid
balances, and the Order histogram spreads around the scenario's terminal.

## Not done (documented seams, per V1/V2 discipline)

- **By account** tab is a labeled placeholder (consolidated only for now).
- Order tab is throwaway — the full sequence-risk decomposition (conditional failure q_i,
  order-share s_order) remains the future prototype this previews.
