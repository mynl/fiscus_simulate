# fiscus_simulate — Plan Overview

High-level map of the whole build. Detail for each stage lives in its own
`dev/plan-<version>-stageN-*.md`; this file is the one-screen summary. The
`CHANGELOG.md` is the record of what landed.

## What we're building

A vectorized Monte-Carlo retirement simulator for a two-person household: ~100k
scenarios × 160 quarters (40 yrs), reporting success/failure measures, percentile
trajectories and a net-worth funnel. Full spec in `initial_ask.md`. The engine is the
core asset — pure NumPy, no Flask, no pandas in the hot path. The eventual purpose
(see the author's blog post, saved in memory) is to explain the *geometry* of
failure — return-environment vs. sequence risk, scenario discovery — not to emit one
"probability of success". V1 is the scaffold that keeps those seams open.

## Locked decisions (2026-07-07)

| Topic | Decision |
|---|---|
| **Deployment** | Two separate servers, one shared look. `fiscus_simulate` is a **standalone** Flask app cloning the house style; it **never imports `fiscus_project`**. Dependency is one-way: **`fiscus_project` may import `fiscus_simulate`**, so this package must stay a clean, importable library. `fiscus_project` = factual/high-security; `fiscus_simulate` = no private data, higher compute. |
| **Cross-platform** | **Hard requirement** — must run on Windows *and* the author's Linux VPS. `pathlib.Path` only; no `C:\` literals; no OS-specific calls in package code; test-portable. `csv-grid` is installed on the server, so it's a normal dependency (still keep it out of the pure-engine import path). |
| **Config format** | **YAML** (matches both siblings + house rules), consistent throughout. `pyproject.toml` is the only TOML. |
| **Package layout** | Mirror `fiscus_project`: engine modules at `src/fiscus_simulate/` top level, web in a `web/` subpackage (`app.py` factory + `routes.py` + `state.py` + `views.py`). |
| **Config models** | Proposed: **pydantic v2** for typed models + validation + round-trip + schema version. (Alt: dataclasses + hand-written `validate()`. Confirm at Stage 1.) |
| **Versioning** | SemVer from **1.0.0**; each stage bumps the minor (1.0.0 → 1.1.0 → … → 1.7.0). Keep `pyproject.toml` + `__init__.__version__` in sync. |
| **Commits** | `X.Y.Z short summary` one-liner; detail in `CHANGELOG.md`; ends with Co-Authored-By. Commit per stage. Never push. |
| **Venvs** | `.venv` is a machine-local **junction** into `V:\dev\venvs\fiscus_simulate` on Windows (plain `.venv` on the VPS). Never committed; keeps venv churn off the NAS-synced AI tree. |

## V1 simplifications that keep it small (author, 2026-07-07)

The "100k × 160 is huge" worry is deliberately engineered away in V1:

- **Constant (deterministic) inflation → one nominal spending path** shared by *all*
  scenarios. Category rates may differ but are constant, so the liability is a single
  `(160,)` (or `(6, 160)` by category) vector, not a `(100k, 160)` cube.
- **Fixed spending-category mix**, "stick to plan" mode (no adaptive cuts — expose
  failure honestly).
- **The only stochastic driver in V1 is asset returns.** Everything downstream that's
  random (portfolio value, withdrawals, realized gains, investment-income tax) flows
  from that one source. This isolates the *return environment* as the star, exactly
  matching the end-state framework.
- Stochastic overall/category inflation, zarr-backed chunked storage, and the full
  path cube are **V2** — the generator API still emits inflation arrays (constant in
  V1) so nothing needs re-architecting. `zarr` is the intended later store for large
  chunked results; not needed at V1 scale.

*Consequence for the engine:* stochastic arrays are `(n_scenarios, n_periods)` per
asset class / account-asset cell; deterministic arrays (spending, inflation) are
`(n_periods,)`. Chunk over scenarios so 100k stays practical, but at V1 sizes a single
in-memory run is fine.

## Stage roadmap (commit + minor bump per stage)

| Stage | Version | Deliverable | Detail plan |
|---|---|---|---|
| 1 | 1.0.0 | Package skeleton, typed config models, YAML serialization, validation, minimal Flask registration, tests | `plan-1.0-stage1-skeleton.md` |
| 2 | 1.1.0 | Deterministic quarterly engine: household, fixed spend, balances, deterministic returns/inflation, income, flat tax, proportional withdrawals, success/failure tracking, **reconciliation tests** | tbd |
| 3 | 1.2.0 | Stochastic **return** generator (correlated GBM/lognormal), generator interface, income/capital split, constant-inflation arrays, seed determinism | tbd |
| 4 | 1.3.0 | Vectorized multi-path execution, chunking, summary stats, percentile trajectories, failure summaries, sampled paths, perf checks | tbd |
| 5 | 1.4.0 | Persistence: run directories, config+metadata, summary Parquet, cache policy, reproducibility metadata (versions, git hash, seed) | tbd |
| 6 | 1.5.0 | Web configuration workflow: config pages, validation, run form, saved configs, Bootstrap + csv-grid | tbd |
| 7 | 1.6.0 | Results site + charts: summary, funnel, terminal-wealth dist, failure dates, representative paths, saved-run list, comparison | tbd |
| 8 | 1.7.0 | Sequence-risk prototype: fix a return environment, permute order, rerun, estimate conditional failure `q_i`, order-sensitivity share `s_order` | tbd |

## Working rules (from CLAUDE.md)

Propose/plan before coding; move a plan to `dev/done/` only when the author says
done; YELL if a stage balloons; keep `CHANGELOG.md` and `dev/TODO.md`
current; NumPy docstrings; label V1 simplifications plainly in the UI.

## Decisions confirmed 2026-07-07
- **Inflation V1 = constant/deterministic**, single shared nominal spending path
  (category rates constant-but-differentiated); stochastic inflation is V2. The only
  stochastic driver in V1 is asset returns. ✓
- **Config models = pydantic v2.** ✓

## Still open (AQIN, not blocking Stage 1)
- **Cross-site nav** — for "one look", a shared top-nav that links across to the
  `fiscus_project` site in V1, or matching style now + cross-links later? (Stage 6.)
