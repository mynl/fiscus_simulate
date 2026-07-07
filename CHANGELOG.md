# Changelog

All notable changes to `fiscus_simulate`. Semantic versioning from 1.0.0; each build
stage bumps the minor. Newest first.

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
