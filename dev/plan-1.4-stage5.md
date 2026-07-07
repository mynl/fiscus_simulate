# Plan 1.4 — Stage 5: Persistence & reproducibility

**Goal:** persist a run's compact outputs to a filesystem run directory, capture full
reproducibility metadata, and add cache management (list / load / delete / prune / pin).
Never persist the full scenario cube. **Version 1.4.0.**

**In scope:** `storage.py`; run directories under the app-state dir; Parquet summaries;
reproducibility metadata; cache policy; load & delete; wire `service.run_simulation` to
optionally persist. **Out of scope:** web (Stage 6/7), sequence risk (8).

## 1. Run directory layout

Under `AppState.runs_dir` (`~/.fiscus_simulate/simulation_runs/`, app state — **never the
repo**):

```
simulation_runs/<run_id>/
    config.yaml          the exact RunConfig (YAML, consistent with the app)
    metadata.json        reproducibility metadata (below)
    summary.parquet      scalar summary: success rates, terminal stats, overall rate
    percentiles.parquet  net-worth percentile trajectories (period x {p1..p99}) + deflator
    failures.parquet     failure-timing counts by period (+ never)
    scalars.parquet      percentile tables for min-nw / years-funded / tax / sales
    paths.parquet        OPTIONAL bounded representative sample (guarded by config)
    PINNED               marker file if the run is protected from auto-prune
```

*Config is YAML* (the app's one format), not the ask's `config.toml` example — noted for
consistency. `run_id` = `YYYYMMDDTHHMMSSZ-<4hex>` (UTC timestamp + short suffix);
readable, sortable, collision-safe. `datetime.now(UTC)` is fine here (normal Python).

## 2. Reproducibility metadata (`metadata.json`)

run_id; created (ISO UTC); seed; generator name; **package version**
(`fiscus_simulate.__version__`); **git commit hash** where available (subprocess
`git rev-parse`, `None` off a checkout — e.g. the VPS install); Python version; key
dependency versions (numpy, pandas, pyarrow, pydantic); n_scenarios; horizon; runtime_s;
completion status (`complete` / `failed`); warnings; and a **summary checksum** (hash of
the percentile + summary arrays) so a rerun with the same code+config+seed can be
verified byte-for-byte.

## 3. `storage.py` API

- `save_run(result, config, runs_dir=None) -> Path` — write the directory; returns it.
- `load_run(run_id) -> LoadedRun` — read metadata + summary tables (lazy on paths).
- `list_runs() -> list[RunInfo]` — id, created, n_scenarios, success rate, size, pinned.
- `delete_run(run_id)` / `delete_details(run_id)` (drop paths.parquet, keep summaries).
- `pin(run_id, on=True)` — toggle the PINNED marker.
- `prune(max_age=None, max_bytes=None)` — remove oldest unpinned runs past limits;
  **never delete a pinned run**; also auto-clean incomplete/temp runs. Returns what was
  removed (and `log`s it — no silent truncation).

Pandas/pyarrow enter **only here** (the persistence boundary). Arrays → tidy DataFrames.

## 4. Service wiring

`run_simulation(config, persist=False, runs_dir=None)` — when `persist`, call
`save_run` after summarizing and return the run directory in `meta`. Keeps the engine
Flask-free and persistence opt-in for interactive/test use.

## 5. Tests

- Round-trip: save → load returns equal summary arrays; metadata fields present;
  checksum stable for same seed, and a rerun reproduces it.
- Parquet files exist and reload via pandas; config.yaml round-trips to an equal RunConfig.
- Cache: `list_runs` sees saved runs; `delete_run` removes; `delete_details` keeps
  summary; `pin` protects from `prune`; `prune(max_bytes/max_age)` removes the right runs.
- All against a **temp `runs_dir`** (tmp_path) — never the real app-state dir.

## 6. Decisions (proceeding unless you object)

1. **Run config persisted as YAML** (app-consistent), not the ask's `config.toml`.
2. **`run_id` = UTC-timestamp + 4-hex suffix** (readable/sortable).
3. **Persistence is opt-in** from `run_simulation(persist=...)`; the web layer (Stage 6)
   turns it on for real runs.
