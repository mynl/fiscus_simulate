# fiscus_simulate

Retirement cash-flow and asset Monte-Carlo simulation for a two-person household.
Part of the Fiscus family; **stands alone** (`fiscus_project` may import it, never the
reverse). A vectorized NumPy engine surrounded by typed configuration, persistence, and
an optional Flask web layer — the engine is the core asset and never imports Flask.

> Scenario simulation, **not a forecast**. V1 is deliberately simplified and labels its
> approximations in the UI. See `dev/plan-overview.md` for the full roadmap and
> `initial_ask.md` for the specification.

## Status

**Stage 1 (v1.0.0): package skeleton + configuration.** Typed, validated,
YAML-round-trippable `RunConfig`; a minimal Flask app that boots. No engine yet —
the deterministic quarterly engine is Stage 2. Changelog: `CHANGELOG.md`.

## Requirements

- Python **>= 3.13**, managed with **uv**. Cross-platform (Windows + Linux VPS).

## Setup

Windows dev keeps the virtualenv off the NAS-synced tree by putting it on the local
dev drive `V:\dev` via a junction:

```powershell
New-Item -ItemType Directory -Force V:\dev\venvs\fiscus_simulate | Out-Null
New-Item -ItemType Junction -Path .venv -Target V:\dev\venvs\fiscus_simulate  # before first sync
uv sync --extra dev
```

On the Linux VPS just use a normal `.venv` (`uv sync --extra dev`).

```sh
uv run pytest            # run the test suite
uv run fiscus-simulate   # serve the web app on http://127.0.0.1:5057 (needs --extra web/dev)
```

## Layout

```
src/fiscus_simulate/     engine (top level) + web/ subpackage
    models.py            typed RunConfig (pydantic v2)
    config.py            YAML load/save/validate
    engine.py …          engine pieces (stubs until Stage 2+)
    returns/ analysis/   generators; summaries & sequence risk
    web/                 Flask factory, routes, house-style templates
assets/branding/         logo/favicon source-of-truth (see its README)
fixtures/                synthetic example config (safe, committed)
tests/                   pytest suite
dev/                     plans and TODO
```

Configuration is YAML; no database (pandas + Parquet/Feather come with the engine).
Web binds `127.0.0.1` by default.
