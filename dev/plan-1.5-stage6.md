# Plan 1.5 — Stage 6: Web configuration workflow

**Goal:** let the author build/edit a `RunConfig`, save it by name, and **launch a
persisted simulation from the browser** — the first end-to-end "drive it from the web"
stage. Results *rendering* (funnel, charts, csv-grid tables) is Stage 7; Stage 6 shows
only enough of a run's outcome to confirm it completed. **Version 1.5.0.**

**In scope:** config editor + validation, named saved-config store, run launcher with
duplicate-submit protection, a minimal run-status/list view, `web/` wiring.
**Out of scope:** the results dashboard + charts + csv-grid tables (Stage 7); sequence
risk (Stage 8); structured per-field widget forms for the matrix sections (see §2).

---

## ⚠️ YELL — this is the biggest stage, and one lever controls its size

Everything else in Stage 6 is small filesystem + routing glue. The cost driver is **how
we edit the config**. The `RunConfig` tree has ~40 scalars *plus* three nested dicts
(`category_pct`, `category_excess_mean`, per-account `balances` 3×3 + `taxable_basis`)
and two 3×3-ish matrices (`correlations`, and the returns dicts). Rendering all of that
as structured HTML widgets — with server-side coercion, per-field error mapping, and
matrix inputs — is a **large** amount of fragile form plumbing for a single-user local
tool. So I'm flagging the choice before building. See §2; pick A, B, or a split.

---

## 1. What the page set looks like

Mirror the `web/` house shape (single blueprint, `create_app` factory). New routes on
the existing `simulate` blueprint:

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | dashboard — now lists **saved configs** + **recent runs** (was a stub) |
| `/config/new` | GET | start from `RunConfig.default()` |
| `/config/<name>` | GET | open a saved config in the editor |
| `/config/<name>` | POST | validate + save (stay on page; show errors or "saved") |
| `/config/<name>/delete` | POST | remove a saved config |
| `/config/<name>/run` | POST | launch a simulation from this config → redirect to run status |
| `/runs` | GET | list persisted runs (`storage.list_runs`) |
| `/runs/<run_id>` | GET | run status / minimal outcome (full view = Stage 7) |
| `/runs/<run_id>/status` | GET | JSON job status (polled while running) |

All POSTs are **POST-redirect-GET**; the submit button disables on click. Everything
binds localhost (unchanged).

## 2. The config-editor decision (the lever) — **need your call**

**Option A — YAML editor (KISS, recommended).** One editor page: a `<textarea>` holding
the config YAML, a "Load default" button, inline section anchors + help, and a
**Validate/Save** that runs `config.from_yaml_str` server-side. Pydantic already gives
precise, field-path error messages — we just render them. You hand-edit YAML anyway;
the nested dicts/matrices are *natural* in YAML and *painful* as widgets. ~1 template,
~1 small parse/error-format helper. Full editing power, ~5% of the code.

**Option B — structured widget forms.** Eight sub-forms (household, spending, inflation,
balances+basis, returns, income, tax, run controls) with typed inputs, matrix grids,
add/remove income-stream rows, and server-side reassembly into `RunConfig`. Prettier and
more discoverable; **much** larger, and the matrix/dict coercion is the fragile part.

**Option C — split (my actual recommendation if A feels too raw).** Structured widgets
for the *flat scalar* sections that map cleanly (household people, spending total/mode,
inflation means, tax rates, income streams, sim controls) **+ a raw-YAML sub-panel** for
the two matrix-heavy sections (`balances`/`basis`, `return_generator`). ~70% of B's
polish for ~40% of its code, and no fragile matrix widgets.

I recommend **A** for 1.5.0 (fast, full-power, gets you running sims this stage), and
treat structured forms as a later polish bump if you want them. Say the word if you'd
rather I do C. **B I'd push back on** unless discoverability for a non-you user is a V1
goal.

## 3. Saved-config store

Named YAML configs under a new app-state dir: `~/.fiscus_simulate/configs/<name>.yaml`
(add `AppState.configs_dir`, created lazily; cross-platform, no drive literals). Thin
helpers (in a small `web/configs.py` or extend `state.py`): `list_configs()`,
`load(name)`, `save(name, cfg)`, `delete(name)`. Names are slugified + validated
(`[a-z0-9-_]`) to keep them filesystem-safe. Reuses `config.save_config`/`load_config`
— no new serialization path.

## 4. Running a sim — sync vs. background — **need your call**

A browser-launched run must handle both interactive (10k, ~2s) and the big run (100k,
~22s). A 22s synchronous request blocks the dev server and risks a proxy timeout on the
VPS, and you explicitly want to *watch it go*. Two shapes:

- **Sync (simplest):** POST runs in-request, redirects to the run view when done. Fine
  at ≤~20k; ugly at 100k (spinner, then a long hang). Zero new state.
- **Background thread + poll (recommended):** POST spawns a daemon thread that calls
  `run_simulation(persist=True)`, registers a job in an in-process dict, and redirects to
  `/runs/<run_id>` which polls `/status` (queued → running → complete/failed) and then
  shows the outcome. ~40 lines of job registry; single process, localhost, so no real
  concurrency risk. One code path for all sizes and it's the honest way to show a 22s run.

I recommend **background thread + poll**. It directly answers "see it in action" and
doesn't fall over at 100k. Duplicate-submit protection = disabled button **+** the job
registry refusing a second in-flight job for the same config (idempotent).

*Note:* the dev server is single-threaded by default; the run must not wedge the UI, so
the worker thread is needed even for the status page to poll. `app.run(threaded=True)`
(or waitress in `--prod`) covers it.

## 5. csv-grid — **defer to Stage 7**

Config pages are forms, not tables; the `csv_grid.to_html` payoff is the **results**
tables in Stage 7. So Stage 6 uses plain Bootstrap tables for the config/run lists and
we settle the csv-grid dev/VPS distribution question when it actually earns its keep.
This also keeps the Windows-local `[tool.uv.sources]` path off the critical path this
stage. (Flag if you'd rather wire it now.)

## 6. Minimal run view (Stage 6 only)

`/runs/<run_id>` shows: status, config name, n_scenarios, seed, runtime, overall success
rate, terminal-wealth median, and first-failure summary — a plain table + the
"V1 simplifications" note. **No funnel/charts** (Stage 7). Enough to confirm the run
worked and is persisted.

## 7. Tests

- Routes: dashboard/list/editor GET 200; new-config seeds from default; save round-trips;
  invalid YAML re-renders with the pydantic error (no 500); slug validation rejects bad
  names; delete removes.
- Run launch: POST creates a job, `/status` transitions to `complete`, a run dir is
  persisted (temp state dir), and a second identical in-flight submit is refused.
- All against an injected `AppState(state_dir=tmp_path)` — hermetic, no real app-state
  dir, no `C:\` literals (extends `test_portability`).

## 8. Decisions (proceeding unless you object)

1. **Config editing = Option A (YAML editor)** unless you pick C (split) — this is the
   one I most want your nod on before I build.
2. **Runs execute in a background thread with a polled status page** (not sync).
3. **csv-grid deferred to Stage 7**; Stage 6 uses plain Bootstrap tables.
4. **Saved configs** live in `~/.fiscus_simulate/configs/<name>.yaml`.
5. **Cross-site nav to `fiscus_project`: defer** (match style now, cross-link later) —
   still parked, non-blocking.

Give me a nod on §2 and §4 and I'll build.
