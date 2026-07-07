# fiscus_simulate

Retirement cash-flow and asset Monte-Carlo simulation for a two-person household.
A new package in the Fiscus family (siblings: `../fiscus_project` — the main
planning/budgeting app; `../fiscus_download` — the CSV-gathering helper). The full
V1 specification is in `initial_ask.md`; this file is the operating guide.

Author: Stephen J. Mildenhall — PhD in math, actuary, geeky. Lead with the
mathematical framing; quantitative formulations (optimization, probability, risk
measures, variance decomposition) are the intended design language, not decoration.

**Status: greenfield.** Only `initial_ask.md` + `.gitignore` exist so far. Nothing
is built. Architecture is under discussion — propose before building.

## What it is (V1 scope, in one breath)

A vectorized NumPy engine simulates ~100,000 scenarios × 160 quarterly periods (40
years) of a household's spending, income, taxes, portfolio withdrawals and returns,
then reports success/failure measures, percentile trajectories and a net-worth
funnel. Deliberately simple but structurally extensible: every major feature has an
explicit V1 form and a documented V2 extension path. The engine is the core asset —
Flask, charts and persistence sit *around* it and must not contaminate its numerical
design. **The engine must not import Flask.**

Guiding philosophy: transparent assumptions, reproducible calculations, scenario
thinking over false precision, explicit failure (V1 sticks to planned spending and
does NOT smooth away ruin), and separation of return-environment risk from
sequence-of-returns risk. A simulated path is one possible future, never a forecast.

## Working with the author

These rules apply in every project — follow them without being re-asked.

- **Diagnose / design / propose before editing source or tests.** Don't change code
  until told to proceed ("go ahead"). "Can you see the issue?" means explain, not fix.
- **YELL when a request is involved.** The author assumes his asks are easy. If one
  implies a big jump in code size or a drop in speed, say so first and let him decide.
  His need for speed outweighs his occasional whims. (This whole project is large —
  see "How we should proceed".)
- **KISS.** Prefer 90% the easy way over 100% via a hellacious complication.
  Difficulty is a signal to stop and talk, not to push through with a fragile hack.
- **CHALLENGE / be a thought-partner.** Check requests for consistency (naming,
  conventions, the TOML-vs-YAML and layout notes below). He can forget or misspeak;
  flag anything that looks off rather than silently complying.
- **When you have enough to act, act.** Don't re-litigate settled decisions or narrate
  options you won't pursue. Give a recommendation, not an exhaustive survey.
- Keep rendered output tight — no gratuitous blank lines. US spelling throughout
  (prose, docstrings, comments, identifiers — "behavior", "color"). ISO dates.
- Periodically remind the author to stop biting his tongue.

### Steve-terminology
- **SWIM** — "see what I mean": you have enough context; fill gaps sensibly.
- **AQIN** — "ask questions if needed": on genuine ambiguity, ask rather than guess.
- **gummage** — is or would be perfection (Chandler Bing). "That's gummage" = exactly right.
- He often multitasks — wait for input.

## Environment & tooling

- **PowerShell on Windows.** No `awk`/`sed`/`head`/`tail` (even via the Bash tool).
  Use `rg` + the Read/Edit/Write tools.
- **Python >= 3.13**, managed with **uv**. `hatchling` build backend, `src/` layout.
- `pathlib.Path` for all file manipulation. **Never hardcode absolute paths** — use
  config; create lazily.
- **No env vars for configuration** — use config files. (`.env` only ever for
  secrets, which this package has none of.)

```
uv sync --extra dev      # sync environment with dev extras
uv run pytest            # run the test suite (primary test mechanism)
uv run python ...        # run anything in the managed environment
```

Do NOT run the 100k-path performance benchmark as part of routine verification —
it is a non-default, opt-in test. Iterate at 1,000 (correctness) / 10,000
(interactive) paths; note the big run as pending and let the author trigger it.

## Data & storage conventions (match the siblings)

- **No database.** Human-readable config + pandas + Parquet/Feather + small JSON/TOML
  metadata + filesystem run directories. Prefer visible files to DBs.
- **Config format = YAML** to match `fiscus_project` and `fiscus_download` (the ask
  says "TOML or YAML per existing Fiscus conventions" — siblings are YAML). *Note the
  ask's run-dir example writes `config.toml`; confirm with the author, but default to
  YAML for consistency.* `pyproject.toml` is of course always TOML.
- **Typed configuration models** with defaults, validation, and round-trip
  serialization tests. Config is the single source of truth for a run.
- Run directories under a `simulation_runs/<run_id>/` tree (config, metadata,
  summary/percentiles/failures Parquet, charts). **Never persist the full
  scenario cube by default** — summaries, percentile trajectories, failure tables and
  chart-ready aggregates only; optional bounded path samples. Cache controls (max age,
  max storage, pin/protect, delete-details-keep-summary, auto-clean incompletes).

## Data firewall & privacy

- **Localhost only.** Web front end binds `127.0.0.1` by default, never `0.0.0.0`;
  make the bind configurable and require a token for any non-localhost bind.
- This package models *assumptions*, not downloaded transactions, so it is far less
  data-sensitive than `fiscus_project`. Even so: no real personal financial figures
  committed — develop/test against synthetic fixtures under `fixtures/`. `.gitignore`
  already blocks `*.parquet`, `*.csv` (except fixtures), `*.local.yaml`, logs.
- **No network egress in core code.** V1 needs none; keep it that way (web-based
  assumption lookup is a documented V2 item, opt-in and pull-public-IN-only if built).

## Architecture (V1 target)

Engine core is pure NumPy; pandas only at config/summary/output boundaries. The web
layer calls a **service layer** that builds configs, runs sims, persists summaries and
returns presentation-ready data — the web never touches the engine directly.

| Module | Role |
|---|---|
| `config.py` / `models.py` | typed run configuration + validation + serialization |
| `engine.py` | vectorized quarterly simulation loop (no Flask, no pandas in the hot path) |
| `spending.py` / `income.py` / `assets.py` / `tax.py` | the modeling pieces |
| `returns/` (`base.py`, `gbm.py`) | abstract generator interface + V1 GBM/lognormal |
| `analysis/` (`summary.py`, `sequence.py`) | summary stats; sequence-of-returns prototype |
| `storage.py` | run directories, Parquet summaries, cache policy, reproducibility metadata |
| `service.py` | orchestration seam between web and engine |
| `routes.py` + `templates/` + `static/` | Flask + Bootstrap web area |

*Layout note:* the ask nests `routes.py`/`templates/`/`static/` directly under
`src/fiscus_simulate/`; `fiscus_project` instead uses a `web/` subpackage
(`app.py` factory + `routes.py` + `state.py` + `views.py`). Confirm which shape the
author wants before Stage 6.

**Naming:** subclasses use the `Base<Kind>` prefix form (e.g. a `ReturnsGBM`-style
name sorts with its base), full words for new identifiers. Define canonical orderings
once (spending-category order, asset-class order, account-type order) and enforce
centrally via a pandas Categorical — not ad-hoc per view.

Reuse the siblings' stack where it fits: **Flask + Bootstrap 5.3**, tables rendered
server-side via **`csv-grid`** (`from csv_grid import to_html`; the ask's "custom CSV
grid/viewer"), the `create_app()` factory + single-blueprint house style. Check the
sibling `pyproject.toml` for the `csv-grid` local `[tool.uv.sources]` path.

### Key numerical disciplines (from the ask — non-negotiable)
- **Explicit period indexes and dates**, never bare array positions, for time logic.
- **Real ↔ nominal identity** `1+R^N = (1+r)(1+π)`; income yield and capital return
  kept separate (`R^N = Y + G`); document the compounding convention and never
  silently treat an arithmetic sum as exact. Quarterly-from-annual conversion is
  explicit and tested.
- **One documented order of operations** per quarter (the ask proposes a 13-step
  order); pick one, document it, use it consistently.
- **Reconciliation identities as tests**: ending wealth = beginning + income + capital
  return − spending − tax (adjusted to the chosen ordering), checked every period on
  tiny hand-verifiable deterministic cases (zero return/inflation, single asset class,
  single account, assets exhausted, etc.).
- **Vectorized**: NumPy arrays, no Python loop over scenarios, deterministic seeding,
  chunking for the big run. Mind memory — a single 100k×160 float64 array is ~128 MB,
  and there are many (per account × asset cell); chunk rather than allocate the full
  cube.

## Versioning, changelog, commits

- **Semantic versioning from 1.0.0.** Each feature bumps the minor: 1.0.0 → 1.1.0 →
  1.2.0. Don't crawl 1.0.101 — that should be ~5.20.0. Keep version strings in sync
  (`pyproject.toml` + `__init__.__version__`).
- **Maintain `README.md`** (stable front page) and, critically, **`CHANGELOG.md`**
  (Keep a Changelog / SemVer, newest first, dated). Update the changelog at the close
  of each iteration — don't defer.
- **Commits:** the ask calls for a clean commit after each of its 8 stages, with the
  suggested `feat(simulate): …` messages. Fiscus grants Claude the per-turn local
  commit opt-in (one line, e.g. `1.2.0 short summary`, detail in CHANGELOG, ending
  with the Co-Authored-By trailer). **Never push.** Before any commit, sanity-check the
  staged file list for data leakage. Confirm the author wants the `feat(simulate):`
  Conventional-Commit style vs. the siblings' `X.Y.Z summary` style.

## Documentation

- **NumPy-style docstrings** (Parameters / Returns / Notes) on every new or modified
  function. For mathematical/algorithmic logic the Notes section explains the *why*.
  Balanced docstrings + comments; maintainable, readable.
- **UI must plainly label the V1 simplifications**: flat-rate taxes, no
  mortality/morbidity, fixed spending mix, proportional withdrawals, no rebalancing,
  stylized return generator. Never present a single "probability of success" as a
  definitive forecast.
- **UI rule:** no buttons that change meaning with state (no play/pause) — use
  separate, explicitly-labeled actions.

## Planning workflow

- Multi-step features get a plan doc in `./dev/plan-<version>-<desc>.md` (version then
  short description; never bare sequence numbers). Move to `./dev/done/` **only when
  the author says it's done** — not when the code lands. `dev/TODO.md` holds the
  roadmap; check it before proposing structural changes.
- Use **[human-readable] type labels** for steps/deliverables ([engine], [web]), never
  A1/A2.

## The V1/V2 discipline (the spine of this project)

`initial_ask.md` §26 lists explicit V1 exclusions (mortality, dynamic spending, tax
law, RMDs, rebalancing, bootstraps, jump diffusion, UMAP/ML scenario discovery, robust
optimization, annuities). **Do not partially implement them.** Leave documented
extension points instead — the abstract return-generator interface, a rebalancing-
policy slot in config, separate success criteria 1–3 that coincide in V1 but diverge
in V2. The long-term goal is not a Monte-Carlo success percentage but a system that
explains *which* futures fail and *why* (environment vs. ordering, inflation,
composition) — keep the path/return APIs able to support the sequence-risk and
scenario-discovery work without building it yet.
