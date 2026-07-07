# Plan 1.1 — Stage 2: Deterministic quarterly engine

**Goal:** a correct, fully deterministic single-path quarterly engine with reconciliation
tests, structured so Stage 3 (stochastic returns) and Stage 4 (vectorization over
scenarios) slot in without redesign. **Version 1.1.0.**

**In scope:** household ages, fixed-mix nominal spending, account/asset balances,
deterministic returns + inflation, external income, flat taxes, proportional
withdrawals with analytic gross-up, taxable cost-basis approximation, success/failure
tracking, reconciliation identities as tests.

**Out of scope (later stages):** stochastic generator (3), vectorized N-path exec (4),
persistence (5), web (6/7), sequence risk (8). No rebalancing, no mortality, no
withdrawal ordering (all V2).

---

## 1. State representation (vectorization-ready from day one)

The scenario axis exists now with size 1. Every stochastic-in-future array carries a
leading `(S,)` scenario dim; deterministic period data is `(T,)`.

- `T = horizon_years * 4 = 160` periods; `A_acct = 3`, `A_asset = 3`.
- `balances`  : `(S, A_acct, A_asset)` float, ≥ 0.
- `basis`     : `(S, A_asset)` cost basis for the **taxable** account only (V1 gain approx),
  **seeded from initial config** (see §6a) so the first sale splits gain vs. principal
  correctly.
- `cash` asset per account doubles as the accumulating cash balance (§2 step 6).
- Period inputs (Stage 2: deterministic, `S = 1`):
  - `spend_nominal`   `(T, K)` by category, and its row-sum `(T,)`  — shared by all S.
  - `inflation`       `(T,)`.
  - `ext_income`      `(S, T)` nominal, plus taxable amount.
  - per asset per period: `total_return`, `income_yield`, `capital_return` `(S, T, A_asset)`
    with `1+total = (1+capital)·... ` consistent (see §4). In Stage 2 these are constant.

The **period loop is Python (160 iterations)**; all work inside is vectorized over `S`.
No Python loop over scenarios — ever.

## 2. Chosen quarterly order of operations (income-first, per author 2026-07-07)

This models how the household actually manages: **spend investment income first, sell
assets only on a shortfall, let excess cash accumulate.** More computation than a
reinvest-everything model, but faithful — which is the point.

Per period `t`, beginning invested balances `B` and cash balances `Ca` per account
(`W_begin = ΣB + ΣCa`):

1. **Ages advance**; determine active income streams (age ≥ start, < end).
2. **Spending** `Sp_t` = precomputed nominal spending (fixed real mix × category inflation).
3. **External income** `X_t` (cash in), with taxable part `X_tax`.
4. **Investment income** on *beginning* invested balances, **paid out as cash** into the
   same account's cash balance (the asset keeps only its capital-return portion):
   interest = Σ B[·,bonds]·y_bonds + B[·,cash]·y_cash; dividends = Σ B[·,stocks]·y_stocks.
5. **Income tax (accrual)**: `tax_income = other_pension_rate·X_tax` + (taxable account
   only) `interest_rate·interest_taxable + dividend_rate·dividend_taxable`. Tax-deferred
   / tax-free investment income is **not** taxed on accrual (deferred → taxed at
   withdrawal; free → never).
6. **Fund from the spendable pool first.** `pool = X_t + spendable_cash` (spendable_cash =
   accumulated + this-period income cash — scope per Decision 1 below). `need = Sp_t +
   tax_income`.
   - `pool ≥ need`: pay it; **surplus `pool − need` accumulates in the taxable cash
     balance** (no sale, no rebalancing). `tax_sale = 0`.
   - `pool < need`: shortfall `Δ = need − pool` → **sell assets** (step 7).
7. **Proportional sale with analytic gross-up.** Raise `Δ` net-of-sale-tax by selling
   proportionally across sellable holdings, weights `w_cell = B_cell / B_sellable`. Sale
   tax is **linear** in gross `G`: `tax_sale = G·τ`,
   `τ = Σ_cell w_cell·r_cell`, `r_cell = tax_deferred_withdrawal` (tax-deferred),
   `= realized_gain_rate · embedded_gain_ratio_cell` (taxable), `= 0` (tax-free).
   Net-of-tax `= Δ ⟹ G = Δ/(1−τ)` — **closed form, no iteration.** (If `τ≥1` or
   `G > B_sellable`: sell all, flag funding failure that period.)
8. **Debit sold cells** by `w_cell·G`; reduce taxable `basis` proportionally
   (`basis ·= 1 − sold_fraction`); record realized gains + `tax_sale`.
9. **Apply capital returns** to end-of-period invested balances (post-sale):
   `B ·= (1 + capital_return)`. Basis unchanged by appreciation. Income cash added to the
   taxable cash balance in step 4 carries basis = its (after-tax) amount.
10. **Record** end balances, `W_end`, cashflows, `tax_total = tax_income + tax_sale`,
    spending, income, sales, realized gains; evaluate outcomes (§5).

**Convention summary:** income paid out and spent first; shortfall covered by
proportional asset sale (analytic gross-up); surplus accumulates as cash; capital
returns applied at period end; tax is account-aware.

## 3. Reconciliation identity (the test backbone)

Both regimes (sell / surplus) collapse to the same per-period identity, and it is
**invariant to the income-first vs. reinvest choice** — income spent vs. held as cash
is a transfer *within* net worth, so it nets out:

```
W_end = W_begin + X_t + investment_income + capital_return − Sp_t − tax_total
```

**Every reconciliation test asserts this holds each period** (to float tol), plus the
cumulative version over the horizon.

## 4. Real ↔ nominal & income/capital split

Primary parameterization is **real** returns. Nominal via `1+R^N = (1+r)(1+π)`.
Split `R^N = Y + G_cap` with `Y` the (deterministic) income yield and `G_cap` the
capital-return residual: `G_cap = R^N − Y` (documented additive convention; note it is a
convention, not an identity of multiplicative compounding). Annual→quarterly conversion
is explicit and tested: quarterly rate `= (1+annual)^{1/4} − 1` for returns and
inflation; yields `annual/4` (documented choice). **These conversions get dedicated unit
tests.**

## 5. Success / failure measures (record all; V1 several coincide)

Per path: (1) portfolio ≥ 0 throughout; (2) housing+core funded throughout; (3) all
planned spending funded throughout; (4) terminal assets > threshold; (5) first-failure
period/date; (6) years funded; (7) min net worth; (8) terminal net worth; (9) total
tax; (10) total withdrawals. Keep 1–3 separate even though they coincide when spending
is inflexible (V2 splits them).

## 6. Module layout (fill the Stage-1 stubs)

- `spending.py` — build `spend_nominal (T,K)` from `SpendingPlan` + `InflationAssumptions`.
- `income.py` — external income schedule; investment-income (yield) computation.
- `assets.py` — balances/basis state; proportional withdrawal + gross-up; return application.
- `tax.py` — income tax + withdrawal tax; transparent per-type breakdown.
- `engine.py` — the period loop orchestrating the order of operations; returns an
  `EngineResult` (arrays + per-path outcome record). Pure NumPy; no Flask, no pandas.
- A tiny **deterministic returns provider** (constant arrays) lives in `engine.py` or a
  `returns/deterministic.py` for Stage 2; Stage 3 swaps in the GBM generator behind the
  same array contract.

### 6a. Config change (author 2026-07-07): initial cost basis

Add **initial taxable cost basis** to the config: for the taxable account, the cost
basis per asset (`stocks`, `bonds`; `cash` basis ≡ its value). A small typed model
(e.g. `initial_basis: {stocks: …, bonds: …}` under a `CostBasis` object or alongside
`balances`), validated `0 ≤ basis ≤ market value`. Tax-deferred/tax-free need no basis
(taxed on full withdrawal / never). This is a **1.1.0 config addition** — round-trip and
validation tests extend accordingly, and `RunConfig.default()` seeds a plausible basis
(embedded gain) so the example run exercises realized-gain tax.

## 7. Tests (deterministic, hand-verifiable — Stage 2 acceptance)

Reconciliation identity every period, plus manually-checkable micro-cases:
zero return & zero inflation; positive deterministic return; deterministic inflation;
no tax; 100% tax-free assets; fully taxable withdrawals; no external income; external
income exceeding spending (surplus regime); assets exhausted mid-horizon (failure
timing); no exhaustion; one asset class only; one account type only. Plus unit tests for
annual→quarterly conversion, real→nominal identity, category allocation, proportional
withdrawal weights, gross-up (`G(1−τ)=N`), cost-basis update, failure detection,
terminal-threshold success.

## 8. Decisions

**Resolved 2026-07-07 (author):** income-first model — spend investment income (and pay
its tax) first, sell on shortfall, accumulate excess as cash, no rebalancing;
account-aware income tax; initial taxable cost basis is config (§6a).

**All confirmed 2026-07-07:**

1. **Spendable pool = external income + taxable-account interest/dividends (+ taxable
   cash).** Income arising inside tax-deferred **and tax-free** accounts accumulates in
   that account's cash and is reached only via the proportional shortfall sale.
2. **Quarterly conversion:** geometric for returns/inflation `((1+a)^{1/4}−1)`,
   `annual/4` for yields — each unit-tested.
3. **Terminal success threshold:** configurable, **default 0** ("not exhausted").
```
