# Plan 1.8.0 — retired default, computed-tax framing, preview matrix, walk columns

Status: **implemented** (stage 1 of 2; 1.9.0 is the engine rework). Awaiting sign-off
before `dev/done/`.

## Scope (config + presentation only — no engine change)

Part of a two-stage batch (see the approved plan). 1.8.0 is the low-risk half.

- **Ask 1 — retired base example + generic preset.** `RunConfig.default()` → two retired
  62-year-olds (A: Social Security 40k @ 67; B: none). Income streams were already optional
  (`Person.income_streams` defaults to `[]`), so no model change. Added `RunConfig.generic()`
  (accumulation-phase demo) + `/config/new?template=generic` + a dashboard button.
- **Ask 2 — removed the `tax` spending category.** Dropped from `SpendingCategory`; default
  mix re-balanced to 100. Computed tax (`TaxRates`, the walk `Tax` column) is unrelated.
- **Ask 5 — preview account × asset matrix.** `preview.py:_account_matrix` builds rows
  (taxable/tax-deferred/tax-free/Total) × columns (stock/bond/cash $, expected income, total
  income, after-tax income); rendered in `config_edit.html`.
- **Ask 3 (light) — walk columns.** `replay_scenario` adds `realized` and
  `unrealized = capital_return − realized_gain`; `_walk_frame` shows BOP balances by asset
  + the flow roll-forward, dropping ending-by-account. Reconciles: `Total change = Income +
  Savings − Expense − Tax + Realized G/L + Δ Unrealized`.

## Deferred to 1.9.0 (engine)

- **Ask 4** — BOP-expense / EOP-income re-timing, cash-first funding, ordered sales
  (taxable → tax-deferred → tax-free), RMDs (default age 75, Uniform Lifetime Table).
- **Ask 3 (full)** — actuarial walk layout + the real per-account "By account" tab (needs
  per-account capture in the engine).

## Verification

`uv run --no-sync pytest -q` → 91 green; `ruff` clean. Walk reconciliation verified on a
replayed scenario. Author smoke: New → retired A/B; New (generic demo) → accumulation
config with a retirement panel; preview shows the account×asset matrix; a Details walk
shows Realized G/L and Δ Unrealized and balances.
