# fiscus_simulate

Adds to `V:\dev\CLAUDE.md` (house rules) and `V:\dev\fiscus\CLAUDE.md` (the family). Project
detail only — see **Deltas** at the foot.

Retirement cash-flow and asset Monte-Carlo simulation for a two-person household. A vectorized
NumPy engine simulates ~100,000 scenarios × 160 quarterly periods (40 years) of a household's
spending, income, taxes, portfolio withdrawals and returns, then reports success and failure
measures, percentile trajectories, and a net-worth funnel.

`initial_ask.md` is the V1 specification; `CHANGELOG.md` is the record of what is built.

Deliberately simple but structurally extensible: every major feature has an explicit V1 form and a
documented V2 extension path. **The engine is the core asset — Flask, charts, and persistence sit
*around* it and must not contaminate its numerical design.**

Guiding philosophy: transparent assumptions, reproducible calculations, scenario thinking over
false precision, explicit failure (V1 sticks to planned spending and does NOT smooth away ruin),
and separation of return-environment risk from sequence-of-returns risk. **A simulated path is one
possible future, never a forecast.**

## Architecture

Engine core is pure NumPy; pandas only at config, summary, and output boundaries. The web layer
calls a **service layer** that builds configs, runs simulations, persists summaries, and returns
presentation-ready data — **the web never touches the engine directly.**

| Module | Role |
|---|---|
| `config.py` / `models.py` | typed run configuration, validation, serialization |
| `engine.py` | vectorized quarterly simulation loop — no Flask, no pandas in the hot path |
| `spending.py` · `income.py` · `assets.py` · `tax.py` · `rmd.py` · `savings.py` · `rates.py` | the modeling pieces |
| `returns/` (`base.py`, `gbm.py`, `deterministic.py`) | abstract generator interface + implementations |
| `analysis/` (`summary.py`, `sequence.py`) | summary statistics; sequence-of-returns work |
| `storage.py` | run directories, Parquet summaries, cache policy, reproducibility metadata |
| `service.py` | the orchestration seam between web and engine |
| `preview.py` | fast pre-run preview |
| `web/` | `app.py` factory + `routes.py` / `views.py` / `state.py` / `charts.py` / `configs.py` / `grid.py` / `jobs.py`, templates, static |

The `web/` subpackage shape matches `fiscus_ledger` — that question is settled by the code; don't
reopen it.

**Naming:** subclasses use the `Base<Kind>` prefix form so a subclass sorts with its base; full
words for new identifiers. Define canonical orderings once — spending-category, asset-class,
account-type — and enforce centrally via a pandas Categorical.

## Key numerical disciplines — non-negotiable

- **Explicit period indexes and dates**, never bare array positions, for time logic.
- **Real ↔ nominal identity** `1+R^N = (1+r)(1+π)`; income yield and capital return kept separate
  (`R^N = Y + G`). Document the compounding convention and **never silently treat an arithmetic
  sum as exact.** Quarterly-from-annual conversion is explicit and tested.
- **One documented order of operations per quarter.** Pick it, document it, use it consistently.
- **Reconciliation identities as tests:** ending wealth = beginning + income + capital return −
  spending − tax, adjusted to the chosen ordering, checked every period on tiny hand-verifiable
  deterministic cases (zero return and inflation, single asset class, single account, assets
  exhausted).
- **Vectorized:** NumPy arrays, no Python loop over scenarios, deterministic seeding, chunking for
  the big run. **Mind memory** — one 100k×160 float64 array is ~128 MB and there are many, per
  account × asset cell. Chunk rather than allocate the full cube.

## Storage

Run directories under `simulation_runs/<run_id>/` — config, metadata, summary / percentiles /
failures Parquet, charts. **Never persist the full scenario cube by default**: summaries,
percentile trajectories, failure tables, and chart-ready aggregates only, plus optional bounded
path samples. Cache controls: max age, max storage, pin/protect, delete-details-keep-summary,
auto-clean incompletes.

Saved scenario configs live under `<state_dir>/configs/`. On DOOB that directory is a junction
into the settings tree (`~/.fiscus/settings/simulate`) so the authored scenario documents are
backed up; the code treats it as a plain directory and must keep working when it is one (VPS).

## Deltas from house rules

- **The engine must not import Flask**, and pandas stays out of the hot path. This is the
  project's central architectural constraint, not a style preference.
- **Do NOT run the 100k-path performance benchmark as routine verification.** It is a non-default,
  opt-in test. Iterate at 1,000 paths for correctness and 10,000 for interactive work; note the
  big run as pending and let the author trigger it.
- **The glossary rule is load-bearing.** Every web page showing *computed* numbers carries a
  bottom-of-page **Glossary** (small font, via the `{% block glossary %}` in `base.html`)
  explaining exactly how each figure is derived — the formula, the convention, the V1/V2 caveat.
  **When you change how a number is computed, update its glossary entry in the same change.** A
  stale glossary is a bug. New computed pages get one; review existing ones whenever their inputs
  change.
- **The UI must plainly label the V1 simplifications** — flat-rate taxes, no mortality or
  morbidity, fixed spending mix, proportional withdrawals, no rebalancing, stylized return
  generator. **Never present a single "probability of success" as a definitive forecast.**
- **The V1/V2 discipline is the spine of this project.** `initial_ask.md` §26 lists the V1
  exclusions. **Do not partially implement an excluded item** — leave a documented extension point
  instead: the abstract return-generator interface, a rebalancing-policy slot in config, separate
  success criteria that coincide in V1 but diverge in V2. Check the CHANGELOG before assuming an
  item is still excluded; some have since been built deliberately. The long-term goal is not a
  Monte-Carlo success percentage but a system that explains **which** futures fail and **why** —
  environment versus ordering, inflation, composition. Keep the path and return APIs able to
  support sequence-risk and scenario-discovery work without building it yet.
- **This app is orthogonal to the family seam.** It does not read `latest-positions.csv`; it
  models *assumptions*, not downloaded transactions, so it is far less data-sensitive than the
  ledger. Even so, no real personal financial figures are committed — develop and test against
  synthetic fixtures.
