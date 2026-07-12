The exact command to fire it up yourself:

uv run fiscus-simulate          # dev server (auto-reload)
uv run fiscus-simulate --prod   # waitress (what's running now)
uv run fiscus-simulate --port 5060   # pick a different port

---

# Status & handoff — 2026-07-12 (paused here)

**Where we are: v1.9.0.** (You committed through 1.8.0; **1.9.0 is in the working tree,
tested & clean but NOT yet committed** — commit it when you're happy: `1.9.0 …`.) Read
CHANGELOG.md + README.md for detail. 104 tests green, ruff clean.

The engine is now the real thing: vectorized NumPy, **life-actuarial order of operations**
(spend at BOP from cash, income/gains/pensions at EOP, reconcile cash to next quarter's
spend), **ordered tax-efficient sales** (taxable → tax-deferred → tax-free, analytic
gross-up per tranche), **RMDs** (Uniform Lifetime Table, default age 75), and **debt-funded
ruin** (keep spending, net worth goes negative — failure = insolvency, min/terminal show
depth). Web: retired A/B default + "generic demo" preset, account×asset preview matrix,
Runs → Summary/Details, Details page (percentile→scenario picker, funnel overlay,
Consolidated + By-account walk, throwaway Order-of-returns experiment), uPlot charts.

**Deferred / simplifications to revisit:**
- **RMD is pooled + elder-age-based** (accounts aren't attributed per person); quarterly RMD
  is ¼ of the annual figure (not a Q4 lump). Fix when accounts get per-person ownership.
- **Withdrawal order** is configurable but only taxable→tax-deferred→tax-free is exercised —
  you said "may want to tweak later" (e.g. tax-bracket-aware / fill-to-bracket).
- **Order-of-returns tab is a throwaway preview** — the real sequence-risk prototype (Stage
  8: variance decomposition environment-vs-ordering, conditional failure qᵢ, order-share) is
  still ahead. This is the seam toward the geometry-of-failure vision (RDM / scenario
  discovery) from your blog post.
- **100k-path performance benchmark** not run routinely — trigger it yourself to validate
  speed/memory at full scale (we iterate at 1k/10k).
- Representative individual-path overlays on the funnel (needs `persist_sample_paths > 0`).
- Preview "expected / total / after-tax income" definitions and the walk's Δ-unrealized
  convention are reasonable but iterate freely if a different framing reads better.

**Future development ideas (mostly documented V2 seams):**
- **Mortality / survival weighting** → report mortality-adjusted P(ruin before death).
- **Stochastic inflation** (`overall_vol` / `category_excess_vol` seams exist, ignored in V1).
- **Rebalancing policy** (config slot exists, unused) and **dynamic/adaptive spending**
  (V1 is "planned" only — the mode field is there).
- Richer return models (bootstraps / empirical / jump diffusion), annuities.
- Per-person accounts → proper per-person RMD and account attribution.
