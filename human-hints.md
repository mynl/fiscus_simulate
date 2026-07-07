# human-hints

High-level log of what we discuss and decide. Newest first.

## 2026-07-07

- **Stage 2 built (v1.1.0): deterministic quarterly engine.** Income-first model
  (Steve's correction — spend div/int first, sell on shortfall, accumulate excess cash,
  no rebalancing). Analytic sale gross-up `G=Δ/(1−τ)`. Initial taxable cost basis added
  to config. Reconciliation identity holds every period (uses *funded* spending, so
  exhaustion shows as a shortfall = the failure). 31 tests green. Sanity: default 40y run
  survives, ends ~£167k from £1.25M.
- **Help offcanvas (v1.0.1):** top-right `?`, terse per-page content, version in its
  footer (off the page). `.gitattributes` LF normalization.
- **Stage 2 conventions confirmed:** spendable = external + taxable-account int/div only
  (tax-free/deferred income stays inside until a sale); geometric qtr conversion,
  yield/4; terminal threshold default 0. Account-aware income tax (taxable only).

- **Stage 1 built (v1.0.0):** package skeleton, pydantic-v2 `RunConfig` with
  validation + YAML round-trip, minimal Flask app that boots, branding wired, tests.
  No engine yet (Stage 2 next).
- **Branding chosen:** the "Roman-style FIS" art `..._4720900e..._2.png` from
  `../fiscus_art` (marked `USED_` there). Favicon set + logos generated with
  ImageMagick into `assets/branding` + `web/static`.
- **Decisions:** standalone app (one-way dep: `fiscus_project` imports us, not the
  reverse); cross-platform is a hard requirement (Windows + Linux VPS); config = YAML;
  layout mirrors `fiscus_project` (`web/` subpackage); commits `X.Y.Z summary`;
  pydantic v2 for config; venvs live on `V:\dev` via a junction.
- **V1 stays small:** constant/deterministic inflation → one shared spending path;
  only stochastic driver is asset returns. Stochastic inflation + zarr chunked storage
  are V2.
- **Repo:** `github.com/mynl/fiscus_simulate`, default branch `master`. Initial docs
  commit pushed.
- **Guiding vision (end state, not V1):** the author's blog post on geometry-of-failure
  retirement modeling — return-environment vs. sequence risk, scenario discovery. V1
  keeps the seams open (abstract return-generator interface, multivariate per-path
  outcomes).
