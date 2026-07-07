# Plan 1.0 — Stage 1: Package skeleton & configuration models

**Goal:** a clean, installable `fiscus_simulate` package with fully typed, validated,
round-trippable run configuration and a minimal Flask app that boots — **no engine
yet**. This stage is deliberately all scaffolding + config; it de-risks everything
downstream because every later stage consumes the `RunConfig`.

**Version:** 1.0.0 → commit `1.0.0 package skeleton and configuration models`.
**Out of scope:** any simulation math, stochastic generators, persistence beyond
config YAML, real web pages. Those are Stages 2–8.

## Deliverables (by [label])

### [scaffold] package tree + build
Mirror `fiscus_project`'s shape. Engine modules stubbed at top level (empty but
importable, with module docstrings + a `# Stage N` marker); `web/` subpackage for
Flask.

```
fiscus_simulate/
    pyproject.toml
    README.md
    CHANGELOG.md
    human-hints.md
    dev/                        # plan-overview.md, this plan, TODO.md
    fixtures/                   # committed synthetic example configs
    src/fiscus_simulate/
        __init__.py             # __version__ = "1.0.0"
        config.py               # load/save/validate entry points (thin)
        models.py               # the typed config models  <-- bulk of this stage
        engine.py               # stub (Stage 2)
        spending.py income.py assets.py tax.py   # stubs (Stage 2)
        returns/__init__.py base.py gbm.py        # stubs (Stage 3)
        analysis/__init__.py summary.py sequence.py  # stubs (Stage 4/8)
        storage.py              # stub (Stage 5)
        service.py              # stub (Stage 4/6 seam)
        web/
            __init__.py
            app.py              # create_app() factory
            routes.py           # single blueprint, side-effect registration
            state.py            # AppState (paths, version)
            views.py            # tiny helpers (mirrors fiscus_project)
            templates/fiscus_simulate/base.html  dashboard.html
            static/fiscus_simulate/
    tests/
```

- **`pyproject.toml`**: hatchling backend, `requires-python = ">=3.13"`, `src/`
  layout, `[tool.pytest.ini_options]` `pythonpath=["src"]`, `[tool.ruff]`
  `line-length=100`. Package (dist) name `fiscus-simulate`, import name
  `fiscus_simulate`.
  - **deps:** `numpy`, `pandas>=2`, `pyarrow>=15`, `pyyaml>=6`, `pydantic>=2`,
    `flask>=3`, `waitress>=3`, `csv-grid`. (numpy/pandas/pyarrow present now so the
    lock is stable even though the engine lands later.)
  - **dev extras:** `pytest>=8`, `ruff>=0.4`.
  - `csv-grid` is **installed on the server**, so it's a normal dependency there; the
    Windows sibling points `[tool.uv.sources]` at a local editable path
    (`c:/s/ai/csv-viewer/python`) which won't resolve on the VPS. Keep the local
    editable source **Windows-dev-only** and put `csv-grid` behind an optional `web`
    extra so a headless engine install never needs it. Keep it out of the pure-engine
    import path regardless.

### [config] typed models — the substance of Stage 1
`models.py`, pydantic v2 (`BaseModel`, `model_config = ConfigDict(extra="forbid")`),
US spelling, NumPy docstrings. Real expected returns as the primary parameterization
(per `initial_ask.md` §9.2). Models:

- `Person` — role label, current_age, pension_start_age, annual_real_pension,
  optional end_age.
- `Household` — exactly two `Person`s (validate len==2), start_date, horizon_years
  (default 40), quarterly convention enum (`calendar_qend` for V1).
- `SpendingPlan` — total_annual_real, `category_pct: dict[Category, float]` over the
  fixed category set (`housing, core, non_core, travel, medical, tax`). **Validate
  Σpct == 100 ± tol.** Canonical category order defined once here.
- `InflationAssumptions` — V1: constant overall rate + constant per-category *excess*
  rates (deterministic). Fields sized for the V2 stochastic form (mean+vol+corr) but
  V1 reads only the means. `π_{k} = π + δ_k`. (Confirms the "one spend path" decision.)
- `AssetClass` enum (`stocks, bonds, cash`); `AccountType` enum
  (`taxable, tax_deferred, tax_free`).
- `AccountBalances` — the `account_type × asset_class → balance` matrix. **Validate
  non-negative.** Helpers: by-account, by-asset, aggregate allocation.
- `ReturnGeneratorConfig` — `type: str` (`"gbm"`), per-asset expected real return,
  volatility, income_yield, and a correlation matrix. Validate matrix symmetric,
  unit diagonal, entries in [-1,1] (PSD check deferred/warn).
- `IncomeStream` — annual_real, start_age, optional end_age, inflation_linking,
  taxable_fraction (or rate). (State-pension / Social-Security-generic.)
- `TaxRates` — flat marginal rates by type: tax_deferred_withdrawal, interest,
  dividend, realized_gain, other_pension. tax_free ≡ 0.
- `WithdrawalPolicy` — V1 fixed `"proportional"`; leave field for future ordering.
- `RebalancingPolicy` — **stub object** (`type="none"`) so config has the slot.
- `SimulationConfig` — n_scenarios, seed, chunk_size, requested outputs, persistence
  settings.
- `RunConfig` — top-level: **`schema_version`**, household, spending, inflation,
  balances, return_generator, income_streams, tax_rates, withdrawal_policy,
  rebalancing_policy, simulation. `default()` classmethod builds a sane example.

### [serialize] YAML round-trip
`config.py`: `load_config(path) -> RunConfig`, `save_config(cfg, path)` via
`yaml.safe_dump`/`safe_load` over `model_dump(mode="json")` / `model_validate`.
Enums serialize to their string values; dates ISO. `schema_version` written and
checked on load (warn/raise on mismatch). Provide `clone()` and `to_yaml_str()`.

### [validate] explicit validators (unit-tested)
Category pct sum; non-negative balances; pct/rate ranges; correlation-matrix shape &
bounds; exactly-two-person household; horizon > 0; n_scenarios > 0. Validation errors
are clear and point at the field.

### [web] minimal boot
Mirror `fiscus_project/src/fiscus/web`: `create_app()` returns a Flask app, registers
one blueprint via side-effect import of `routes`, `AppState` carries version + a
lazily-created app-state dir under `Path.home()/.fiscus_simulate` (config,
`simulation_runs/` later). One route `/` → `dashboard.html` extending a house-style
`base.html` (Bootstrap 5.3 CDN, sticky navbar, wordmark) showing version + "no runs
yet". Bind `127.0.0.1` default, configurable. `csv-grid` NOT imported yet (Stage 6).

### [meta] docs & housekeeping
- `README.md` — purpose, the **V:\dev venv setup recipe** (below), `uv sync`/`pytest`,
  points at CHANGELOG.
- `CHANGELOG.md` — `## 1.0.0` (dated 2026-07-07): skeleton + config models.
- `human-hints.md` — session log, newest first (today's decisions).
- `dev/TODO.md` — roadmap = the 8 stages + parked V2 items.

## Venv setup recipe (Windows, keeps churn off the NAS)
```powershell
New-Item -ItemType Directory -Force V:\dev\venvs\fiscus_simulate | Out-Null
# from repo root, before first sync (no existing .venv):
New-Item -ItemType Junction -Path .venv -Target V:\dev\venvs\fiscus_simulate
uv sync --extra dev
```
On the Linux VPS: no junction — a plain `.venv` (or `UV_PROJECT_ENVIRONMENT`).
`.venv` is already `.gitignore`d; never committed.

## Tests (pytest, all against fixtures — Stage 1 acceptance)
- `RunConfig.default()` constructs and validates.
- Round-trip: `save_config` → `load_config` returns an equal model (deep equality).
- Validation failures raise: pct sum ≠ 100; negative balance; not-two-person
  household; bad correlation matrix; unknown extra field (`extra="forbid"`).
- Category canonical order is stable and complete.
- `schema_version` present in serialized YAML; mismatch handled.
- `create_app()` boots; `GET /` → 200 and contains the version string.
- Portability smoke: no `C:\`/backslash path literals in `src/` (a simple rg-based
  test or manual check).

## Acceptance / done when
`uv run pytest` green; `uv run python -c "import fiscus_simulate; print(fiscus_simulate.__version__)"`
prints `1.0.0`; app boots and serves `/`; a `fixtures/example_config.yaml` round-trips.
Then: bump/confirm 1.0.0, update CHANGELOG, commit `1.0.0 package skeleton and
configuration models`.

## Decisions — confirmed 2026-07-07
1. **pydantic v2** for config models. ✓
2. **Inflation V1 = constant/deterministic, one shared spend path**; only stochastic
   driver in V1 is asset returns. ✓
3. **csv-grid behind an optional `web` extra** so the core/engine install stays
   VPS-portable — proceeding on this basis (revisit at Stage 6).
