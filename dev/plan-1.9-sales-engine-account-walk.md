# Plan 1.9.0 — computed-tax sales engine + actuarial walk

Status: **implemented**. Awaiting sign-off before `dev/done/`.

## Scope (engine stage — the higher-risk half of the batch)

- **Ask 4 — order of operations + ordered sales + RMDs.** New life-actuarial timing
  (expense BOP from cash → EOP income/gains/tax → reconcile cash to next quarter's spend).
  `assets.ordered_sale` (taxable → tax-deferred → tax-free, analytic per tranche);
  `rmd.py` (Uniform Lifetime Table, default age 75); `WithdrawalPolicy` gains
  `kind`/`order`/`rmd_enabled`/`rmd_start_age` (default `kind="ordered"`).
- **Ask 3 (full) — per-account walk.** Opt-in per-account capture in `engine.simulate`
  (`balances_begin_acct`, `income_acct`, `capital_acct`); `ScenarioWalk.account_columns`;
  the real Details **"By account"** tab.

## Author feedback folded in this stage

- **"Keep spending / accumulate debt?"** → yes. Spending is never cut; the shortfall is
  funded by debt (negative net worth). Failure = insolvency (net worth < 0); "years funded"
  = years until insolvent; min/terminal net worth show ruin depth. Fixed the twin bugs:
  period-0 under-funding (all scenarios showed "0 years funded") and the walk's first-quarter
  expense (now the full plan, not the cash-limited amount).
- **Chart y-axis**: strip trailing `.00` (2M not 2.00M); reserve axis width so large/negative
  labels aren't clipped; more margin below charts for the hover legend.
- Terminal histogram clips both tails (deep-debt outliers).

## Verification

`uv run --no-sync pytest -q` → 104 green; `ruff` clean. Verified: reconciliation identity
holds every quarter under the new order; RMD fires exactly at 75; income is genuinely EOP;
ordered/proportional both reconcile; debt-funded ruin gives meaningful negative net worth;
the per-account walk reconciles to the consolidated (begin balances, income, realized,
unrealized all sum across accounts).

## Deferred / follow-ups

- RMD uses the pooled tax-deferred balance and the elder person's age (V1 simplification —
  accounts aren't attributed per person).
- Per-quarter RMD is a smooth ¼ of the annual figure (not a Q4 lump).
