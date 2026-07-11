# Changelog

All notable changes to `fiscus_simulate`. Semantic versioning from 1.0.0; each build
stage bumps the minor. Newest first.

## 1.7.0 — 2026-07-11

Stage 8 — "see inside the simulations": a per-scenario **Details** view with a
quarter-by-quarter walk, a funnel overlay, and a throwaway order-of-returns experiment
(a deliberate preview of the sequence-risk prototype).

### Added
- **Per-scenario outcomes persisted** (`outcomes.parquet`): terminal net worth, first-
  failure period, minimum net worth and total tax per scenario — a bounded marginal
  (~a few MB at 100k paths), *not* the full cube. Preserves scenario identity so a
  terminal-net-worth percentile maps back to actual scenarios. Legacy runs without it are
  reproduced once from the stored seed and cached (`service.scenario_outcomes`).
- **Exact single-scenario replay** (`service.replay_scenario`): regenerates one scenario
  bit-for-bit from the stored seed (streaming return chunks, slicing the one row) and
  reruns the engine with a new opt-in `simulate(..., capture_balances=True)` that records
  consolidated per-asset balances each quarter. The reconciliation identity holds every
  row: `End = Begin + ext_income + invest_income + savings + capital − spend − tax`.
- **Order-of-returns resampler** (`service.resample_order`): permutes the scenario's 160
  quarterly returns (no replacement, identical across assets so cross-asset correlation is
  preserved; inflation constant in V1), reruns the drawdown vectorized over the
  reorderings, and returns terminal-wealth spread — isolating sequence risk from the return
  environment. Throwaway (optional seed, not persisted).
- **Details page** (`/runs/<id>/details`): percentile → scenario picker; scenario tiles
  (terminal, first shortfall); the scenario overlaid (pink) on the net-worth funnel with
  the nominal/real toggle; and a Bootstrap tab control — **Consolidated** (csv-grid walk),
  **By account** ("Not yet implemented" placeholder), **Order of returns** (histogram +
  stats, with a reorderings/seed form). Full glossary per the self-documenting rule.
- **Runs list** now offers **Summary** and **Details** buttons per run.

### Tests
- `capture_balances` columnwise reconciliation; replay terminal-exactness (across chunks,
  incl. the last) and equivalence to a `generate()` slice; order resample multiset-preserved
  and seed-deterministic with matching reference terminal; `outcomes.parquet` round-trip and
  legacy reproduce-on-demand fallback; web Details renders overlay + tabs + order histogram.
  89 tests green.

## 1.6.2 — 2026-07-11

Proportional asset input — one dollar figure per asset class, the rest as fractions.

### Changed (breaking config schema → `schema_version` 1.3)
- **`AccountBalances` redesigned.** Was a full 3×3 dollar matrix + dollar basis; now:
  - `totals` — whole-portfolio **dollars** per asset class (the only dollar input);
  - `tax_deferred_proportion`, `tax_free_proportion` — **fractions (0–1)** of each
    asset-class total held in those account types; the **taxable** account is the implied
    remainder;
  - `taxable_basis_proportion` — cost basis as a **fraction (0–1)** of the implied taxable
    holding.
  Rescaling the totals now holds the composition fixed. Validators: totals ≥ 0, each
  proportion in [0, 1], and `tax_deferred + tax_free ≤ 1` per asset (taxable ≥ 0).
- New method `AccountBalances.amounts()` reconstructs the account × asset dollar matrix;
  `resolved_taxable_basis()`, `total()`, `by_account()`, `by_asset()` keep the same API, so
  the engine (`engine.py`) and preview are one-line changes. Config editor gains a note
  that the proportions are fractions, not percentages; glossary updated (the rule).

### Tests
- `amounts()` reconstruction + taxable-remainder identity; basis = taxable × fraction;
  negative total, out-of-range basis fraction, and `td+tf > 1` all rejected. `_flat_cfg`
  ported to the new fields. Preview/wealth-total figures unchanged (by-asset totals held).
  78 tests green. `fixtures/example_config.yaml` regenerated.

## 1.6.1 — 2026-07-10

### Fixed
- **Charts rendered as empty placeholders.** The `fiscusChart` helper was defined at the
  bottom of `base.html`, *after* the inline chart calls in the page body — so each call
  hit an undefined function (`ReferenceError`) and drew nothing. Moved the definition into
  `<head>` (right after the uPlot load) and deferred the actual build to `DOMContentLoaded`
  so the container also has a real width to size against. Added a regression test asserting
  the helper is defined before the first chart call.

## 1.6.0 — 2026-07-08

Stage 7: results dashboard & charts.

### Added
- **uPlot charts** (CDN `uplot@1.6.30`, matching `fiscus_project`) with a live hover
  cursor. A `web/charts.py` builder emits JSON `data`+`spec`; a single `fiscusChart` JS
  helper in `base.html` adds the hover/axis formatter functions. Charts are fed only from
  the persisted Parquet summaries.
- **Net-worth funnel** on the run view: median with p10–p90 and p30–p70 shaded bands over
  the 160 quarters (accumulation ramp then drawdown), **nominal / real toggle** via the
  stored deflator.
- **Terminal-wealth histogram** (40 bins; top ~1% clipped into the last bin) — computed at
  summarize time and persisted as `terminal_hist.parquet`.
- **Failure-timing** chart: first-shortfall counts by year (or a "nobody ran out" note).
- **Run comparison** (`/runs/compare`): overlay two runs' funnels (median + p10–p90, A
  blue / B pink) with a headline comparison table; entry points on the runs list and each
  run view.
- **Tail-refined percentile grid**: `PCTS` is now dense in the tails (p0.1…p99.9:
  0.1→1 by 0.1, 1→10 by 1, 10→90 by 10, then symmetric). Percentile Parquet columns are
  named `p{value:g}` (`p0.1`, `p50`, `p99.9`). Glossaries updated for the funnel,
  histogram, failure-timing and comparison (the rule).

### Changed
- `analysis/summary.py` gains the histogram and the finer grid; `storage` persists/reloads
  `terminal_hist.parquet` (`LoadedRun.terminal_hist`, `None` on legacy runs). The
  summary checksum changes with the new percentile set (expected, not a regression).

### Deferred
- Representative individual paths overlay (needs `persist_sample_paths > 0`) — a small
  follow-up; the funnel already conveys the distribution.

### Tests
- Tail grid properties; terminal histogram covers all scenarios; percentile columns
  (`p0.1`/`p99.9`) round-trip; histogram round-trips; run view renders the uPlot funnel /
  terminal / failure blocks and the real-scale toggle; two-run comparison renders. 77 green.

## 1.5.4 — 2026-07-08

Pre-retirement accumulation: model the working years between now and retirement.

### Added (breaking config schema → `schema_version` 1.2)
- **`Person.retirement_age`** (`float | None`; `None` = already retired) and
  **`Person.annual_real_savings`** (real $/yr saved into the pooled portfolio while
  working). `default()` retires both at 67 saving 30k/25k.
- **`savings.py`** — `build_savings_path`: per-quarter nominal contributions (real saving
  inflated to nominal, summed over still-working people).
- **Engine accumulation phase.** Spending is **deferred** until the household is fully
  retired (`Household.spending_start_period` = the latest person's retirement); before
  then only net saving is modeled. Contributions are **invested in the taxable account at
  the current portfolio allocation**, with cost basis stepped up (post-tax, no double-tax,
  stays invested). The reconciliation identity gains a `+ savings` term (checked every
  period, deterministic and stochastic).
- **Retirement projection** in the config preview (all real, closed form, no PV):
  years to retirement, total real savings/yr, **estimated real assets at retirement**
  (`W₀(1+r)ᴺ + Σ savings annuity`, `r` = allocation-weighted real return), estimated real
  retirement income (pensions + portfolio yield), the at-retirement withdrawal rate and
  income coverage. Cross-checks against the sim: the closed-form estimate matches the
  Monte-Carlo median real net worth at retirement. Glossary updated (the rule).

### Changed
- `EngineResult` gains `savings` (T,); `spending` now reflects the *active* schedule
  (0 pre-retirement). The default plan's success rate rises markedly — it now accumulates
  for the working years instead of drawing down from the current age.

### Tests
- Pre-retirement accumulation (contributions grow the pool, no spending, reconciles);
  savings term in both reconciliation checks; retirement projection figures (exact at
  r=0). 74 tests green.

## 1.5.3 — 2026-07-08

### Changed
- **csv-grid is now a normal PyPI dependency** (`csv-grid>=3`) of the `web` extra, and
  added to `dev` so tests exercise the real grid renderer (not the fallback). The
  Bootstrap-table fallback in `web/grid.py` is kept as defensive-only for headless
  installs. `uv.lock` updated (resolves from PyPI — cross-platform).

### Added
- **Delete a saved configuration from the dashboard** (red trash after Run). It unlinks
  the file directly — no load/validate — so a config that no longer parses (e.g. an older
  schema that now fails pydantic) can still be removed without opening the editor.

### Tests
- Dashboard offers a config delete; an unparseable config can still be deleted. 72 tests.

### Notes (recorded for Stage 7 / V2, not yet built)
- Stage 7 charts will use **uPlot** (same lib as `fiscus_project`).
- Stage 7 percentile grid is **tail-refined** (p0.1..p99.9, dense in the tails).
- **Survival-weighted failure** (mortality-adjusted P(ruin before death)) is flagged for
  the V2 mortality work — an unconditional failure rate overweights late ruin the
  household is unlikely to live to see.

## 1.5.2 — 2026-07-08

Friendlier run results, delete-a-run, and self-documenting glossaries.

### Added
- **Delete a run** from the dashboard, the runs list, and the run view (trash button,
  confirm dialog) → `POST /runs/<run_id>/delete` (`storage.delete_run`).
- **Glossary** (`base.html` `{% block glossary %}`, small font, page bottom, rendered
  only when defined): plain-language notes on how each computed figure is derived. Added
  to the run view (success criteria, nominal/real, tax composition, percentile-vs-joint)
  and the config editor (wealth, portfolio income, withdrawal rates). New **CLAUDE.md
  rule**: a number's glossary entry is updated in the same change as the calc — a stale
  glossary is a bug.
- **Outcome distribution** on the run view: transposed (rows = mean + p01…p99, columns =
  human-titled metrics), rendered with **csv-grid** (`web/grid.py`; optional import with
  a static Bootstrap-table fallback so headless/CI still works). Two views:
  **Percentiles** (each column sorted independently) and **By terminal net worth** (the
  new joint frame — each row is one real scenario, so it reads across coherently). The
  joint outcomes + scalar means are computed at summarize time and persisted as
  `joint.parquet` + `metadata.scalar_means`.

### Changed
- Run view redesigned: **human-titled headline metrics first** (overall success, plan
  funded, portfolio solvent, terminal wealth mean/median), the outcome distribution next,
  and **reproducibility metadata moved to a collapsed section at the bottom**.
- `analysis/summary.py` gains `scalar_means` and `joint_by_terminal`; `storage` persists
  and reloads them (`LoadedRun.joint`, `None` on legacy runs).

### Tests
- Joint frame + means round-trip; terminal-ranked rows monotone in terminal net worth;
  run view shows human headline + taxes + glossary; terminal view renders; delete-a-run
  removes it. csv-grid `to_html` verified against the table shape. 70 tests green.

## 1.5.1 — 2026-07-08

Pre-Stage-7 refinements: income model cleanup, editor rename semantics, config preview,
and surfaced taxes.

### Changed (breaking config schema → `schema_version` 1.1)
- **Income streams now nest under each person** (`Person.income_streams`), removing the
  redundant top-level `income_streams` list and its `owner` cross-reference. The engine
  already read only the streams; the `Person`-level pension scalar fields
  (`pension_start_age`, `annual_real_pension`, `pension_end_age`) were dead and are gone.
  A stream gains an optional `label` (e.g. "state pension").
- **`Person.role` → `Person.name`** (the person's name; the `owner` key it backed is
  gone). The `_income_owners_exist` validator is removed (nothing to cross-check now).
  `fixtures/example_config.yaml` regenerated to the new shape.

### Added
- **Config preview** (`preview.py` → `config_preview`, pure/closed-form, no engine run):
  household wealth (total + by account), gross portfolio income and the estimated
  taxable-account tax at t=0, pensions (total, active-now, years to first), planned
  spending, and the implied **gross** and **net** initial withdrawal rates. Rendered as
  a card on the editor after save (default: 4.8% gross / 2.6% net).
- **Rename-on-save = new scenario**: the editor name field is editable when editing a
  saved config; changing it and saving writes a new scenario and keeps the original.
- **Taxes surfaced** on the run view: p10/p50/p90 of lifetime taxes paid (plus assets
  sold, terminal/minimum net worth, years funded), read from `scalars.parquet`. (Taxes
  were always computed — interest, dividends, pension, tax-deferred withdrawals, realized
  gains — just not shown.)

### Tests
- Nested income streams round-trip; person-without-streams; preview figures
  (wealth/income/tax/withdrawal-rate exact); active-pension-now; editor renders the
  preview; rename creates a new scenario; run view shows lifetime taxes. 68 tests green.

## 1.5.0 — 2026-07-07

Stage 6: web configuration workflow — drive a persisted simulation from the browser.

### Added
- **Config editor** (`web/routes.py` + `config_edit.html`): a YAML editor seeded from
  `RunConfig.default()`, validated server-side via `config.from_yaml_str`. Field-level
  pydantic errors render inline (`views.format_config_error`); nothing is written until
  it validates — malformed YAML or an invalid config re-renders, never a 500.
- **Named saved-config store** (`web/configs.py`): configs live at
  `~/.fiscus_simulate/configs/<name>.yaml`; names are slugified + validated to a
  filesystem-safe form. `AppState.configs_dir` (created lazily).
- **Run launcher** (`web/jobs.py`): a browser-launched run persists via
  `run_simulation(persist=True)`. Small runs (≤ `SYNC_THRESHOLD` = 20,000 scenarios)
  execute inline; larger ones run in a **daemon thread** with a polled status page
  (`job_status.html`) so the UI never wedges on a ~22 s 100k run. The `JobRegistry`
  refuses a second in-flight run for the same config (duplicate-submit protection,
  reinforced by a disabled submit button).
- **Views**: dashboard now lists saved configs + recent runs; `/runs` list; a minimal
  `/runs/<run_id>` view (reproducibility metadata + summary metrics + the V1
  simplifications note). Full funnel/charts remain Stage 7.
- Flash messaging (per-process session key) for save/delete feedback.

### Notes
- csv-grid tables deferred to Stage 7 (config pages are forms, not tables); Stage 6 uses
  plain Bootstrap tables. Cross-site nav to `fiscus_project` still parked.

### Tests
- Editor round-trip; slugified names; invalid-YAML and validation-error re-render
  (no 500); empty-name rejected; delete. Run launch persists a run and views it;
  job-view redirects to the completed run; missing-config 404; registry refuses a
  duplicate in-flight job. All against an injected temp state dir. 63 tests green.

## 1.4.0 — 2026-07-07

Stage 5: persistence & reproducibility.

### Added
- `storage.py` — the persistence boundary (pandas/pyarrow live only here). Saves a run to
  `~/.fiscus_simulate/simulation_runs/<run_id>/`: `config.yaml`, `metadata.json`, and
  Parquet `summary` / `percentiles` / `failures` / `scalars` (+ optional `paths` gated by
  `persist_sample_paths`). The full scenario cube is never persisted.
- **Reproducibility metadata**: run_id (`YYYYMMDDTHHMMSSZ-<hex>`), timestamp, seed,
  generator, package version, git commit (where available), Python + dependency versions,
  n_scenarios, horizon, runtime, status, warnings, and a **summary checksum** so a rerun
  with the same code+config+seed verifies byte-for-byte.
- **Cache management**: `list_runs`, `load_run`, `delete_run`, `delete_details`
  (drop paths, keep summary), `pin`/`is_pinned` (protect from prune), `prune`
  (age / size limits + incomplete-run cleanup; never removes a pinned run; returns what
  it dropped).
- `service.run_simulation(persist=..., runs_dir=...)` — opt-in persistence recording
  `run_id`/`run_dir` in `meta`.

### Tests
- Save/load round-trip (config + percentile values), checksum reproducibility,
  optional-paths + delete-details, list/delete, pin-protects-prune, incomplete cleanup,
  run-id shape — all against a temp runs dir. 52 tests green.

## 1.3.0 — 2026-07-07

Stage 4: vectorized execution & result summaries.

### Added
- `service.py` — `run_simulation(config)` orchestrates **chunked** execution over the
  scenario axis (the full return cube never lives in memory), aggregates per-scenario
  outcomes, and returns a `SimulationResult` (summary + representative paths + meta with
  timing). `make_generator` selects GBM/deterministic by config.
- `analysis/summary.py` — `SimulationSummary` + `summarize`: success rates (per criterion
  + overall), failure-timing counts, **percentile trajectories** (1/5/10/25/50/75/90/95/99)
  for the funnel (stored nominal + a `deflator` for real), terminal & scalar
  distributions, representative success/fail path sampling.
- Generators gain `iter_chunks(n, chunk)`; GBM streams from one RNG so chunking is
  **bit-identical** to a single `generate(n)`. Deterministic broadcasts (zero-copy) to N.
- `scripts/benchmark.py` — opt-in 100k perf check.

### Tests
- `iter_chunks` == single generate; chunked run == unchunked (rates + trajectories);
  summary invariants (rates in [0,1], monotone percentiles, failure accounting, deflator);
  real ≤ nominal; representative-path bounds; deterministic-via-service. 44 tests green.

### Performance
- 100,000 paths × 160 quarters in ~22 s (~4,500 paths/s), 128 MB retained (`net_worth`
  only). Chunk size 10,000. (Opt-in; not part of routine tests.)

## 1.2.0 — 2026-07-07

Stage 3: stochastic return & inflation generator.

### Added
- `returns/base.py` — `ReturnsBundle` contract (arrays `(S, T, n_asset)`, including
  `nominal_total` = the realized return environment, the Stage 8 seam) and the
  `ReturnGenerator` ABC.
- `returns/gbm.py` — V1 correlated GBM/lognormal generator: real returns via Cholesky of
  the config correlation matrix, quarterly vol `sigma*sqrt(1/4)`, log-return centered on
  the geometric quarterly mean (so vol=0 reduces exactly to the deterministic provider),
  constant inflation, deterministic yield, seeded RNG for reproducibility.
- `returns/deterministic.py` — refactored to the shared `ReturnsBundle` + a
  `DeterministicReturns` generator class.

### Changed
- Engine consumes returns as `(Sr, T, n_asset)` and broadcasts over the account axis;
  the scenario count comes from the supplied bundle. The reconciliation identity is
  model-agnostic and holds on stochastic runs.
- `pyproject.toml`: `[tool.uv] link-mode = "copy"` (the `.venv` junction lives on the V:
  dev drive; silences the hardlink-fallback warning).

### Tests
- Shapes/axis order, seed reproducibility, zero-vol == deterministic, income/capital
  split, statistical recovery (mean/vol/correlation on a large sample), and engine
  reconciliation on a stochastic run. 37 tests green.

### Notes
- Performance: 10,000 paths × 160 quarters in ~1.6s locally. Chunking + summaries are
  Stage 4; the default plan shows a ~50% success rate (fixed-real 4.8% over 40y) —
  failure is exposed, not smoothed.

## 1.1.0 — 2026-07-07

Stage 2: deterministic quarterly engine.

### Added
- `engine.py` — vectorized quarterly engine (scenario axis present, size 1 in Stage 2)
  implementing the **income-first order of operations**: spend investment income first,
  cover shortfalls by a proportional asset sale with an **analytic tax gross-up**
  (`G = Δ/(1−τ)`, no iteration), accumulate surplus as cash, apply capital returns at
  period end. `EngineResult` carries per-period arrays and per-path outcome measures
  (first-failure period, years funded, min/terminal net worth, totals, success criteria).
- `spending.py`, `income.py`, `assets.py`, `tax.py` — spending path, external income,
  proportional-sale mechanics + cost-basis roll-forward, flat income tax.
- `returns/deterministic.py` — constant return provider (Stage 3 swaps in the generator
  behind the same array contract).
- `rates.py` — annual↔quarterly conversions (geometric returns/inflation, yield/4) and
  the real→nominal identity.
- Config: **initial taxable cost basis** (`AccountBalances.taxable_basis`) so sales split
  gain vs. principal; `SimulationConfig.terminal_threshold` (success criterion 4).

### Tests
- Reconciliation identity `W_end = W_begin + income + return − funded_spending − tax`
  every period; hand-verifiable micro-cases (pure drawdown, surplus accumulation,
  exhaustion/first-failure); gross-up unit tests (tax-deferred, taxable gain, unfunded);
  rate conversions; basis validation. 31 tests green.

### Notes
- Reconciliation uses **funded** spending: when the portfolio is exhausted, actual
  spending falls below plan and the gap is the recorded failure (V1 exposes failure).

## 1.0.1 — 2026-07-07

### Added
- Top-right `?` **help offcanvas** (Bootstrap, mirrors fiscus_project): terse,
  per-page `{% block help %}` content; **version info moved into the help footer** so it
  stays available to the dev without cluttering the page. Added Bootstrap JS bundle +
  bootstrap-icons.

### Changed
- Removed the on-page version display (now in the help pane only).

### Tidy
- `.gitattributes` normalizes line endings to LF (ends the CRLF churn on Windows).

## 1.0.0 — 2026-07-07

Stage 1: package skeleton and configuration models.

### Added
- `src/` package layout with hatchling build; `pyproject.toml` (core deps: numpy,
  pandas, pyarrow, pyyaml, pydantic; optional `web` and `dev` extras).
- Typed configuration models (`models.py`, pydantic v2): `RunConfig` and its subtree
  (household, spending, inflation, balances, return generator, income, tax rates,
  withdrawal/rebalancing policy slots, simulation config). Canonical orderings for
  spending categories, asset classes and account types defined once via enums.
- Validation: category percentages sum to 100, non-negative balances, exactly-two
  household, valid correlation matrix, rate/fraction ranges, income owners exist,
  unknown fields rejected (`extra="forbid"`).
- YAML serialization (`config.py`): human-readable, exact round-trip, schema-version
  check.
- Minimal Flask web layer (`web/`): app factory, single blueprint, house-style
  Bootstrap templates, dashboard stub labelling the V1 model simplifications.
- Branding: "Roman-style FIS" logo + favicon set (`assets/branding/`, served from
  `web/static`).
- Engine/generator/analysis/storage/service module stubs marking their stage.
- Tests: config construction/validation/round-trip, web boot, cross-platform
  no-drive-letter guard.

### Notes
- V1 simplification confirmed: constant (deterministic) inflation → one shared nominal
  spending path; the only stochastic driver is asset returns. Stochastic-inflation
  fields exist but are ignored by the (future) V1 engine.
