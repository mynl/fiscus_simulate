# TODO / roadmap

Stage roadmap (one commit + minor bump per stage). Detail in `plan-overview.md`.

- [x] **1.0.0 Stage 1** — package skeleton, config models, YAML serialization,
      validation, minimal Flask boot, tests.
- [x] **1.1.0 Stage 2** — deterministic quarterly engine + reconciliation tests.
      (income-first model; analytic sale gross-up; cost-basis; success measures.)
- [x] **1.2.0 Stage 3** — stochastic return generator (correlated GBM), generator
      interface, income/capital split, constant inflation arrays, seed determinism.
- [x] **1.3.0 Stage 4** — vectorized multi-path execution, chunking, summaries,
      percentile trajectories, failure summaries, sampled paths, perf checks.
- [x] **1.4.0 Stage 5** — persistence: run dirs, metadata, summary Parquet, cache
      policy, reproducibility metadata.
- [ ] **1.5.0 Stage 6** — web configuration workflow (pages, validation, run form,
      csv-grid); settle csv-grid distribution for the VPS.
- [ ] **1.6.0 Stage 7** — results site + charts (funnel, terminal wealth, failure
      dates, representative paths, comparison).
- [ ] **1.7.0 Stage 8** — sequence-risk prototype (permute a fixed return environment,
      conditional failure `q_i`, order-share `s_order`).

## Parked / open questions
- Cross-site nav to `fiscus_project` in V1, or matching style now + cross-links later?
  (Stage 6.)
- csv-grid on the VPS: publish/pin vs. installed system-wide (Stage 6).
- Transparent / dark-mode logo variant (Stage 6/7 polish).

## Parked V2 (documented extension points, do NOT partially build)
Mortality/morbidity, dynamic spending mix, spending cuts, utility valuation, detailed
UK/US tax, tax-optimized withdrawal ordering, RMDs, rebalancing, historical/block
bootstraps, jump diffusion, stochastic volatility, stochastic inflation, scenario
discovery / PRIM, UMAP, ML variable importance, robust optimization, annuities, LTC,
full path-cube persistence (zarr).
