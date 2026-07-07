# Plan 1.2 — Stage 3: Stochastic return & inflation generator

**Goal:** an abstract return-generator interface plus a correlated GBM/lognormal V1
generator, emitting the same array contract the deterministic provider already uses, so
the engine consumes either unchanged. Deterministic seeding. **Version 1.2.0.**

**In scope:** generator interface (`returns/base.py`), V1 GBM (`returns/gbm.py`),
correlated real returns via Cholesky, constant (V1) inflation, income/capital split,
seed reproducibility, generator tests. Small engine refactor to carry a scenario axis on
the returns arrays.

**Out of scope:** vectorized multi-path *summaries* (Stage 4), stochastic inflation,
bootstraps / fat tails / stochastic vol (V2). Inflation stays **constant** in V1.

## 1. The returns contract (moves to `returns/base.py`)

`ReturnsBundle` (shared by every generator), arrays in `ASSET_CLASSES` order:

- `capital_return`  `(S, T, n_asset)` — what the engine applies to balances.
- `income_yield`    `(S, T, n_asset)` — deterministic in V1 (`annual/4`).
- `nominal_total`   `(S, T, n_asset)` — the **realized return environment** per path;
  first-class so Stage 8 can hold it fixed and permute the `T` axis.
- `overall_inflation_q : float` — constant quarterly overall inflation (V1).

`ReturnGenerator` (ABC): `generate(n_scenarios) -> ReturnsBundle`. Implementations:
`DeterministicReturns` (constant; `S`-broadcast) and `GBMReturns`.

**Engine refactor:** index returns as `[:, t, :]` → `(Sr, n_asset)` and broadcast
(`[:, None, :]`) over the account axis. `Sr` is 1 (deterministic) or `S` (GBM). Existing
tests unchanged (deterministic broadcasts over `n_scenarios`).

## 2. V1 GBM generator

Per asset, per quarter, real total return is lognormal; assets correlated via the
config correlation matrix; inflation constant; yield deterministic.

- **Quarterly vol** `s_q = sigma_annual * sqrt(1/4) = sigma_annual / 2`.
- **Centering (convention — confirm):** center the **geometric** mean on the
  deterministic quarterly figure `g_q = (1+r_real_annual)^(1/4) − 1`, i.e. log-return
  `X ~ N(m, s_q^2)` with `m = ln(1+g_q)`. Then `q_real = exp(X) − 1` has geometric mean
  `g_q` (matches the deterministic provider exactly at `sigma=0`); its arithmetic mean is
  higher by the usual vol drag. Documented; the alternative is to center the arithmetic
  mean on `g_q`.
- **Correlation:** `Z = L · standard_normal`, `L = cholesky(correlation)`; if not PSD,
  raise a clear error (nearest-PSD repair is a V2 nicety).
- **Nominal & split:** `nominal_total = (1+q_real)(1+pi_q) − 1` with
  `pi_q = (1+overall_mean)^(1/4) − 1`; `income_yield = annual_yield/4` (constant);
  `capital_return = nominal_total − income_yield`.
- **Seed:** `rng = np.random.default_rng(config.simulation.seed)` → reproducible.

Consistency check baked into tests: **GBM with all vols = 0 equals the deterministic
provider** (same geometric means).

## 3. Tests (Stage 3 acceptance)

- Shapes and `ASSET_CLASSES` column order.
- **Seed reproducibility**: same seed → identical arrays; different seed → different.
- **Zero-vol == deterministic** (capital_return/nominal_total match).
- Statistical recovery on a large `S`: sample correlation of log-returns ≈ config
  correlation; sample vol ≈ `s_q`; geometric mean ≈ `g_q` (loose tolerances).
- Real→nominal consistency and the income/capital split identity.
- Engine still runs against a GBM bundle; reconciliation identity holds per period for a
  stochastic run (the identity is model-agnostic).

## 4. Decision (proceeding unless you object)

- **GBM centering** on the **geometric** quarterly mean (matches the deterministic
  engine and the ask's "expected real return" read most naturally as a compound figure).
  Say the word if you want arithmetic-mean centering instead — it's a one-line change.
