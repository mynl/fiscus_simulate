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
- [x] **1.5.0 Stage 6** — web configuration workflow: YAML config editor + validation,
      named saved-config store, background run launcher + status page, run views.
      (csv-grid deferred to Stage 7.)
- [x] **1.6.0 Stage 7** — results charts: uPlot funnel (nominal/real), terminal-wealth
      histogram, failure-timing, run comparison; tail-refined percentile grid
      (`p{value:g}` naming). Representative-paths overlay deferred (needs
      `persist_sample_paths`).
- [ ] **1.7.0 Stage 8** — sequence-risk prototype (permute a fixed return environment,
      conditional failure `q_i`, order-share `s_order`).

## Parked / open questions
- Cross-site nav to `fiscus_project` in V1, or matching style now + cross-links later?
  (Stage 6.)
- Transparent / dark-mode logo variant (Stage 6/7 polish).
- **Mortality-adjusted / survival-weighted failure probability** (author flag, 2026-07-08).
  An unconditional "prob of default" overweights *late* failures the household is unlikely
  to live to see — a year-40 ruin matters little at a ~5% survival probability. When
  mortality curves land (V2), report **survival-weighted** failure = P(ruin before death),
  and probably a per-period conditional-on-alive failure hazard, not just the raw path
  failure rate. **Remind the author when building mortality.** Pairs with the sequence-risk
  work — failure timing already exists, this reweights it. See parked V2 (mortality).

## Parked V2 (documented extension points, do NOT partially build)
Mortality/morbidity, dynamic spending mix, spending cuts, utility valuation, detailed
UK/US tax, tax-optimized withdrawal ordering, RMDs, rebalancing, historical/block
bootstraps, jump diffusion, stochastic volatility, stochastic inflation, scenario
discovery / PRIM, UMAP, ML variable importance, robust optimization, annuities, LTC,
full path-cube persistence (zarr).
