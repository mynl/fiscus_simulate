# human-hints

High-level log of what we discuss and decide. Newest first.

## 2026-07-07

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
