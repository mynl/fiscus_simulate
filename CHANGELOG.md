# Changelog

All notable changes to `fiscus_simulate`. Semantic versioning from 1.0.0; each build
stage bumps the minor. Newest first.

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
