# `fiscus_simulate`: Initial Agent Ask

## 1. Purpose

Add a new Python package named `fiscus_simulate` alongside the existing Fiscus packages, including `fiscus_project` and `fiscus_download`.

`fiscus_simulate` will provide retirement cash-flow and asset simulations for a two-person household. It will support the broader Fiscus philosophy of:

- transparent assumptions;
- reproducible calculations;
- scenario-based rather than falsely precise forecasting;
- explicit identification of success and failure;
- separation of return-environment risk from sequence-of-returns risk;
- eventual exploration of robust retirement strategies across broad scenario spaces.

The first implementation should be deliberately simple but structurally extensible. Build a complete vertical slice comprising:

- a tested Python simulation engine;
- configuration models;
- persisted configuration and compact results;
- Flask and Bootstrap pages;
- simulation execution;
- summary tables;
- initial visualizations;
- reproducibility metadata.

The work should proceed in natural stages, with a clean commit after each stage.

Do not attempt to implement every eventual feature in V1. Each major feature should have an explicit V1 implementation and a documented V2 extension path.

## 2. Existing environment

The existing application uses:

- Python;
- Flask;
- Bootstrap;
- pandas;
- Feather and Parquet files;
- a custom CSV grid/viewer.

Avoid introducing a conventional database unless an existing Fiscus architectural requirement makes one unavoidable. Prefer:

- human-readable configuration files;
- pandas DataFrames;
- Parquet or Feather for tabular data;
- small JSON or TOML metadata files;
- filesystem-based run directories and indexes.

Follow the generic project rules supplied separately.

## 3. Package structure

Create a new top-level package:

```text
fiscus_simulate/
```

Use a modular structure along the following lines, adapting names to the existing Fiscus conventions:

```text
src/
    fiscus_simulate/
        __init__.py
        config.py
        models.py
        engine.py
        spending.py
        income.py
        assets.py
        tax.py
        returns/
            __init__.py
            base.py
            gbm.py
        analysis/
            __init__.py
            summary.py
            sequence.py
        storage.py
        service.py
        routes.py
        templates/
            fiscus_simulate/
        static/
            fiscus_simulate/
        tests/
```

The simulation engine must not depend on Flask. The web layer should call a service layer that constructs configurations, runs simulations, persists summaries and returns presentation-ready data.

## 4. Core modelling philosophy

The simulation should distinguish:

1. the household spending liability;
2. external income;
3. investment income;
4. portfolio capital returns;
5. taxes;
6. withdrawals;
7. account and asset balances;
8. success and failure criteria.

The engine should initially use a conventional probability model, but its architecture should support later scenario-based and robust analyses.

A simulated path should be regarded as one possible future, not as a definitive forecast. All assumptions must be visible and saved with the run.

## 5. Time convention

### V1

Use quarterly time steps over a 40-year horizon:

```text
40 years × 4 quarters = 160 periods
```

Use a configurable starting date.

For UK-oriented reporting, support a fiscal-quarter convention in which Q1 is treated as the quarter ending near the end of the UK tax year. For V1, use calendar quarter-end dates unless the existing Fiscus date conventions provide a better implementation:

- Q1: 31 March;
- Q2: 30 June;
- Q3: 30 September;
- Q4: 31 December.

The difference between 31 March and the formal UK tax-year end on 5 April is immaterial for the initial quarterly model. Document that simplification.

All internal time-dependent calculations should use explicit period indexes and dates rather than relying on array positions alone.

### V2

Allow:

- exact UK tax-year periods ending 5 April;
- monthly simulation;
- variable retirement horizons;
- stochastic mortality horizons;
- morbidity and care-state transitions.

## 6. Household model

### V1

Model one household containing two people.

For each person store:

- name or role label;
- current age;
- state pension or Social Security starting age;
- annual real state pension or Social Security amount;
- optional end age for the income stream.

The system should not yet simulate mortality. Both people remain present throughout the 40-year horizon unless an income stream is explicitly configured to end.

Although the application is UK-oriented, use a generic income-stream model so that either UK State Pension or US Social Security-style income can be represented.

### V2

Add:

- mortality tables;
- joint-survival states;
- survivor pension rules;
- morbidity states;
- long-term-care states;
- household spending changes following death or disability.

## 7. Spending model

### V1

The user supplies:

- total annual real household spending;
- percentage allocation across spending categories.

Initial categories:

- housing;
- core;
- non-core;
- travel;
- medical;
- tax.

Definitions:

- `housing`: housing costs, maintenance and related recurring costs;
- `core`: basic and essential non-housing consumption;
- `non_core`: somewhat optional recurring spending;
- `travel`: travel and similar discretionary spending;
- `medical`: healthcare and medical spending;
- `tax`: taxes included in the spending plan rather than taxes calculated directly by the tax model.

Validate that category percentages sum to 100%, subject to a small numerical tolerance.

Convert annual real spending to quarterly real spending. The initial category mix remains fixed over the simulation horizon.

Provide a Flask page to:

- enter total annual spending;
- enter category percentages;
- view annual and quarterly amounts by category;
- validate the spending mix;
- save the configuration.

V1 supports only a “stick to planned spending” mode. Planned expenditure does not decline when assets become strained. The purpose is deliberately to expose failure in the same spirit as conventional fixed-real-withdrawal analyses.

Do not attempt to assign utility or value to spending below plan in V1.

### Inflation treatment

Each spending category has its own simulated inflation rate, correlated with overall inflation.

Use a simple factor form such as
$$\pi_{k,t}=\pi_t+\delta_{k,t},$$
where:

- \(\pi_t\) is overall inflation;
- \(\delta_{k,t}\) is the category-specific excess inflation rate.

For V1, configuration should allow:

- mean overall annual inflation;
- annual overall inflation volatility;
- mean annual excess inflation by spending category;
- annual volatility of excess inflation by category;
- correlation of each category’s inflation with overall inflation.

A simpler equivalent parameterization is acceptable if it produces transparent correlated category inflation.

The engine should simulate nominal spending internally or retain enough information to report both real and nominal spending consistently.

### V2

Add:

- age-dependent spending-mix migration;
- reduced travel with age;
- increased medical spending with age;
- household-state-dependent spending;
- discretionary-spending adjustment rules;
- minimum essential spending;
- desired versus actual spending;
- spending shortfall severity;
- externally researched inflation assumptions;
- web-based assumption lookup with user override;
- stochastic irregular expenditure shocks.

## 8. Asset model

### V1 asset classes

Support three asset classes:

- stocks;
- bonds;
- cash.

### V1 account types

At minimum, distinguish:

- taxable accounts;
- tax-deferred accounts;
- tax-free accounts.

Use generic names internally. The model should be capable of representing accounts such as:

- taxable brokerage;
- traditional pension or 401(k)-type accounts;
- Roth or ISA-like tax-free accounts.

Each account contains balances by asset class.

The initial configuration should therefore define a matrix:

```text
account type × asset class → initial balance
```

Provide pages to:

- enter balances;
- inspect balances by account;
- inspect balances by asset class;
- inspect aggregate asset allocation;
- validate that balances are non-negative.

### V1 withdrawals

When external and investment income do not cover spending and taxes, withdraw proportionally across the available portfolio.

Use a clearly specified rule. A reasonable initial rule is:

1. determine the required net withdrawal;
2. calculate each account-asset cell’s proportion of total available wealth;
3. withdraw that proportion from each cell;
4. apply applicable taxes;
5. gross up withdrawals iteratively or analytically where necessary to fund both spending and withdrawal tax.

The exact implementation should be documented and tested.

Do not implement tax-optimized withdrawal ordering in V1.

### V1 rebalancing

Do not rebalance in V1. Asset weights evolve naturally with returns and withdrawals.

The configuration and result model should nevertheless leave room for a future rebalancing-policy object.

### V2

Add:

- configurable withdrawal ordering;
- tax-aware withdrawals;
- required minimum distributions;
- annual or quarterly rebalancing;
- tolerance-band rebalancing;
- target glide paths;
- tax consequences of rebalancing;
- additional asset classes;
- annuities;
- property;
- liabilities and debt.

## 9. Return model

## 9.1 Generator interface

Define an abstract return-generator interface from the outset.

A generator should accept:

- simulation count;
- period count;
- time-step convention;
- asset-class definitions;
- inflation assumptions;
- random-number generator or seed;
- generator-specific parameters.

It should return aligned arrays or DataFrames for:

- nominal total return by asset class;
- real total return by asset class;
- income yield by asset class;
- capital return by asset class;
- overall inflation;
- category inflation.

Use efficient array representations. Avoid creating one Python object per scenario-period.

## 9.2 V1 generator

Implement one simple generator first.

A suitable V1 implementation is a correlated multivariate geometric Brownian motion or lognormal return generator for stocks, bonds and cash.

Configuration should include, by asset class:

- expected annual nominal or real total return;
- annual volatility;
- income yield;
- capital-return component;
- correlations between asset-class returns.

Choose one primary parameterization, preferably real expected returns plus overall inflation. Derive nominal returns consistently.

If \(r_{a,t}\) is the simulated real return for asset class \(a\), and \(\pi_t\) is overall inflation, use
$$1+R_{a,t}^{N}=(1+r_{a,t})(1+\pi_t),$$
where \(R_{a,t}^{N}\) is the nominal total return.

Income and capital gains must remain separate. For each asset class:
$$R_{a,t}^{N}=Y_{a,t}+G_{a,t},$$
where \(Y_{a,t}\) is income yield and \(G_{a,t}\) is the capital-return component, subject to the exact compounding convention adopted by the implementation.

Avoid silently treating the arithmetic sum as exact if multiplicative compounding is used. Document the convention.

For V1, it is acceptable for income yield to be deterministic and for capital return to absorb the stochastic residual.

The quarterly conversion of annual parameters must be explicit and tested.

## 9.3 V2 generators

Plan interfaces for:

- IID historical bootstrap;
- block bootstrap;
- regime or stationary bootstrap;
- fat-tailed return models;
- jump-diffusion equity returns;
- stochastic volatility;
- autocorrelated returns;
- user-supplied scenarios;
- externally supplied capital-market assumptions;
- separate yield and capital-appreciation processes;
- correlated return, inflation and interest-rate models.

Do not implement all V2 generators in the initial pass.

## 10. Income model

### V1 external income

Support state pension or Social Security-style income for each household member.

Each stream should specify:

- annual real amount;
- start age;
- optional end age;
- inflation-linking rule;
- taxable proportion or income tax rate.

Convert annual amounts to quarterly amounts.

### V1 investment income

Track separately:

- interest;
- dividends;
- realized capital gains;
- unrealized capital gains.

At minimum:

- cash and bonds may generate interest;
- stocks may generate dividends;
- asset-price appreciation generates unrealized capital gains;
- taxable sales may realize gains.

A fully correct tax-lot model is not required in V1. Use a documented approximation for the taxable-gain fraction of taxable-account sales.

Possible V1 approximation:

- store taxable cost basis by account and asset;
- update cost basis for purchases or reinvestment;
- calculate the proportional embedded gain when assets are sold;
- realize that proportion of the sale as a capital gain.

The agent should prefer a simple, internally consistent basis model over an opaque shortcut.

### V2

Add:

- employment and consulting income;
- defined-benefit pensions;
- annuity income;
- rental income;
- survivor benefits;
- income escalation rules;
- benefit caps and taxation rules;
- detailed dividend and interest models.

## 11. Tax model

### V1

Use flat marginal tax rates by income type.

Configuration should include separate rates for:

- tax-deferred account withdrawals;
- interest income;
- dividend income;
- realized capital gains;
- other taxable pension income.

Tax-free account withdrawals have a zero rate.

Apply taxes quarterly.

The tax calculation should return a transparent breakdown by:

- person where applicable;
- income type;
- account type;
- quarter;
- scenario.

Avoid modelling full UK or US tax law in V1.

The user has complex tax circumstances. The V1 model is intentionally a simplified approximation and must be labelled accordingly in the interface and output.

### V2

Add:

- tax bands and allowances;
- UK-specific rules;
- US-specific rules where required;
- required minimum distributions;
- account-specific treatment;
- capital-loss carryforwards;
- tax-lot selection;
- joint versus individual taxation;
- configurable tax jurisdictions;
- plug-in tax calculators.

## 12. Quarterly simulation order

Define and document an explicit order of operations. A proposed V1 order is:

1. advance household ages;
2. determine planned real spending by category;
3. apply category inflation to obtain nominal spending;
4. determine external income;
5. generate investment income;
6. calculate tax on external and investment income;
7. use available cash income to fund spending and tax;
8. calculate the remaining funding requirement;
9. make proportional portfolio withdrawals;
10. realize and tax gains or taxable account distributions;
11. gross up withdrawals as necessary for withdrawal-related tax;
12. apply capital returns to remaining balances;
13. record end-of-quarter balances and outcomes.

The agent should review the timing convention carefully. Returns may instead be applied before withdrawals, but one convention must be chosen, documented and used consistently.

Prefer a convention that allows clear interpretation of beginning balance, income, spending, withdrawals, returns and ending balance.

Add reconciliation identities and tests such as:
$$\text{ending wealth}
=
\text{beginning wealth}
+\text{income}
+\text{capital return}
-\text{spending}
-\text{tax}.$$
The exact identity must reflect the adopted ordering and compounding.

## 13. Simulation scale and performance

Target approximately:

```text
100,000 scenarios × 160 quarterly periods
```

The initial implementation must be designed for vectorized computation.

Requirements:

- use NumPy arrays for the core engine;
- use pandas primarily at configuration, summary and output boundaries;
- do not create a DataFrame containing every field for every path and period unless explicitly requested;
- avoid Python loops over scenarios;
- chunk the simulation if required;
- permit smaller interactive runs;
- support deterministic seeding;
- include basic timing and memory diagnostics.

A reasonable development progression is:

- 1,000 paths for correctness;
- 10,000 paths for interactive testing;
- 100,000 paths for performance validation.

Do not optimize prematurely at the expense of correctness, but structure the engine so that 100,000 paths are practical.

## 14. Simulation outputs

### V1 path-level state

Track enough path-level information to calculate:

- total net worth;
- balances by account type;
- balances by asset class;
- cumulative spending;
- cumulative tax;
- income by type;
- withdrawals by account type;
- realized gains;
- planned and funded spending;
- first failure period;
- terminal assets.

Do not necessarily persist every path-level field.

### V1 success and failure measures

Report all of the following:

1. portfolio remains non-negative throughout the horizon;
2. housing and core spending are fully funded throughout;
3. all planned spending is fully funded throughout;
4. terminal assets exceed a configurable threshold;
5. first failure date;
6. years of spending funded;
7. minimum net worth;
8. terminal net worth;
9. total taxes;
10. total withdrawals.

For V1, because spending remains fixed and the engine does not reduce planned expenditure voluntarily, criteria 1–3 may often coincide. Keep them separate because V2 will distinguish them.

### Summary statistics

For appropriate measures, report:

- mean;
- standard deviation;
- minimum;
- maximum;
- selected percentiles;
- success rates;
- failure counts;
- failure timing distribution.

Use percentiles such as:

```text
1%, 5%, 10%, 25%, 50%, 75%, 90%, 95%, 99%
```

## 15. Visualizations

### V1 funnel graph

Create a net-worth funnel chart over time showing selected scenario percentiles.

At minimum show:

- median;
- 10th and 90th percentiles;
- 25th and 75th percentiles;
- optionally 5th and 95th percentiles.

The chart is primarily visual communication rather than a new statistic.

Make clear that the percentile at each date does not represent one continuous scenario path.

Provide controls for:

- nominal versus real values;
- total wealth;
- account type;
- asset class where practical.

### V1 additional charts

Include:

- histogram or empirical distribution of terminal wealth;
- success/failure summary;
- distribution of failure dates;
- representative successful and failed paths;
- spending, income, tax and withdrawal summaries.

Use the existing Fiscus visual conventions where available.

### V2 red-green and scenario-discovery plots

The long-term goal is not merely to plot success against obvious inputs such as return and spending.

The intended workflow is:
$$(\text{scenario assumptions})\longrightarrow(\text{simulation results})\longrightarrow(\text{classification or regression})\longrightarrow(\text{important scenario structure}).$$
Future analysis should:

- classify scenarios as successful, marginal or failed;
- use machine learning to determine which scenario characteristics explain outcomes;
- measure variable importance or variance reduction;
- use dimensionality reduction such as UMAP to identify lower-dimensional structure;
- produce interpretable two-dimensional red-green maps;
- use scenario-discovery methods to identify regions associated with failure;
- avoid interpreting point density as a genuine probability unless the sampling measure warrants it.

UMAP may be useful for exploratory visualization, but later implementations should preserve an interpretable route back from the embedding to the underlying assumptions.

## 16. Sequence-of-returns and resampling analysis

### V1 or late-V1 prototype

Design the analysis interface for conditional sequence-risk experiments.

Given an already generated path of returns:

1. hold its realized collection of returns fixed;
2. generate alternative orderings;
3. rerun the retirement cash-flow calculation;
4. measure variation caused solely by ordering.

For a result \(Y\), estimate:
$$\mu_i=P_\pi(Y_{i,\pi}\mid R_i),\qquad
v_i=\operatorname{Var}_\pi(Y_{i,\pi}\mid R_i).$$
Across outer return environments, estimate:
$$V_{\mathrm{environment}}=\operatorname{Var}_i(\mu_i),\qquad
V_{\mathrm{order}}=P_i(v_i).$$
Report a descriptive sequence-risk share:
$$s_{\mathrm{order}}
=
\frac{V_{\mathrm{order}}}
{V_{\mathrm{environment}}+V_{\mathrm{order}}}.$$
For the ruin indicator, estimate:
$$q_i=P_\pi(\text{failure}\mid R_i),$$
the proportion of orderings of return environment \(i\) that fail.

A path with \(q_i\approx0\) is robustly adequate. A path with \(q_i\approx1\) is inadequate regardless of ordering. Intermediate values indicate genuine sequence sensitivity.

### Autocorrelation risk

Unrestricted permutations destroy serial dependence. The difference between outcomes under:

- unrestricted annual permutations;
- block permutations;
- cyclic shifts;
- regime-preserving permutations;

can be used to investigate the contribution of serial structure and autocorrelation.

This feature need not be fully implemented in the first vertical slice, but the return-path and simulation APIs must not preclude it.

### V2

Add:

- historical resampling;
- block-size controls;
- stationary bootstrap;
- cyclic shifts;
- path reversal;
- best and worst ordering searches;
- sequence fragility scores;
- comparison of IID and autocorrelated generators.

## 17. Configuration

Use explicit typed configuration models.

A complete run configuration should contain:

- schema version;
- household;
- start date;
- horizon;
- quarterly convention;
- spending assumptions;
- inflation assumptions;
- initial account balances;
- asset allocation;
- return-generator type;
- return-generator parameters;
- external income streams;
- tax rates;
- withdrawal policy;
- rebalancing policy;
- simulation count;
- random seed;
- requested outputs;
- persistence settings.

Configuration should be serializable to a human-readable format, preferably TOML or YAML according to existing Fiscus conventions.

Provide:

- defaults;
- validation;
- round-trip serialization tests;
- a configuration summary page;
- a way to clone an existing configuration;
- a way to export the exact configuration used for a run.

## 18. Reproducibility

Every run must record:

- run identifier;
- creation timestamp;
- configuration;
- random seed;
- generator name;
- generator version;
- package version;
- Git commit hash where available;
- Python version;
- key dependency versions;
- simulation count;
- horizon;
- runtime;
- completion status;
- warnings;
- summary-result checksum where practical.

A rerun with the same code, configuration and seed should reproduce the same results subject to documented numerical limitations.

## 19. Persistence and cache management

Avoid filling the disk with unnecessary path-level data.

Use a run directory structure such as:

```text
simulation_runs/
    <run_id>/
        config.toml
        metadata.json
        summary.parquet
        percentiles.parquet
        failures.parquet
        charts/
        optional_paths.parquet
```

Persist by default:

- configuration;
- metadata;
- summary tables;
- percentile trajectories;
- failure summaries;
- chart-ready aggregates.

Do not persist the complete scenario cube by default.

Allow optional persistence of:

- sampled representative paths;
- failed paths;
- a bounded random sample of paths;
- full results for small runs.

Implement cache controls:

- maximum age;
- maximum total storage;
- protected or pinned runs;
- delete run;
- delete detailed results while retaining summary;
- automatic cleanup of incomplete or temporary runs.

Never delete a pinned run automatically.

## 20. Web interface

Add a `fiscus_simulate` area to the existing Flask website.

### V1 pages

Provide pages for:

1. simulation dashboard;
2. household configuration;
3. spending configuration;
4. inflation assumptions;
5. asset and account balances;
6. return-generator assumptions;
7. income streams;
8. tax rates;
9. run configuration;
10. run execution and status;
11. results summary;
12. funnel chart;
13. tabular output using the existing CSV grid/viewer;
14. saved runs;
15. run comparison;
16. run deletion and cache management.

The dashboard should show:

- configured plans;
- recent runs;
- success rate;
- median terminal wealth;
- selected warnings;
- links to results.

The UI should expose assumptions plainly and avoid presenting a single “probability of success” as a definitive forecast.

## 21. Execution model

A simulation of 100,000 paths may not be suitable for execution directly inside a normal request-response cycle.

Follow existing Fiscus execution patterns where available.

At minimum:

- create a run record or run directory;
- mark the run as pending;
- execute through a service layer;
- update status to running, complete or failed;
- capture errors and diagnostics;
- prevent duplicate execution from repeated form submission.

If there is no existing background-job infrastructure, implement a simple safe initial mechanism without adding an elaborate distributed task system.

The web page should be able to display run status and final results.

## 22. Testing requirements

Build tests alongside each stage.

### Unit tests

Test:

- annual-to-quarterly conversion;
- inflation conversion;
- real-to-nominal return identity;
- category allocation;
- account aggregation;
- income timing;
- tax calculation;
- proportional withdrawals;
- cost-basis updates;
- failure detection;
- terminal-threshold success;
- percentile calculations;
- deterministic seeding;
- serialization round trips.

### Reconciliation tests

For every simulated period, test appropriate cash-flow and balance identities.

Use very small deterministic examples that can be verified manually.

Examples should include:

- zero return and zero inflation;
- positive deterministic return;
- deterministic inflation;
- no tax;
- 100% tax-free assets;
- fully taxable withdrawals;
- no external income;
- external income exceeding spending;
- assets exhausted during the horizon;
- no asset exhaustion;
- one asset class only;
- one account type only.

### Integration tests

Test:

- save configuration;
- run small simulation;
- persist summaries;
- load results;
- render key Flask pages;
- delete cached run.

### Performance tests

Include a non-default benchmark for:

```text
100,000 paths × 160 quarters
```

Record runtime and approximate memory usage, but do not make the full benchmark part of every routine test run.

## 23. Documentation

Provide concise documentation covering:

- package purpose;
- architecture;
- simulation timing;
- configuration schema;
- return parameterization;
- inflation model;
- spending model;
- tax simplifications;
- withdrawal rule;
- success definitions;
- persisted outputs;
- reproducibility;
- current limitations;
- V2 roadmap.

The UI should label model limitations clearly:

- taxes are simplified flat-rate approximations;
- mortality and morbidity are not yet simulated;
- spending mix is fixed;
- withdrawals are proportional;
- no rebalancing occurs;
- the initial return generator is stylized;
- simulation frequencies depend on model assumptions.

## 24. Staged implementation and commits

Build the project in the following stages. Make a clean commit after each stage.

### Stage 1: Package skeleton and configuration

Deliver:

- package structure;
- typed configuration models;
- serialization;
- validation;
- basic Flask registration;
- tests.

Suggested commit:

```text
feat(simulate): add package skeleton and configuration models
```

### Stage 2: Deterministic quarterly engine

Deliver:

- household model;
- fixed spending mix;
- account and asset balances;
- deterministic returns and inflation;
- external income;
- simple taxes;
- proportional withdrawals;
- success and failure tracking;
- reconciliation tests.

Suggested commit:

```text
feat(simulate): add deterministic quarterly retirement engine
```

### Stage 3: Stochastic return and inflation generator

Deliver:

- generator interface;
- V1 GBM or lognormal generator;
- correlated asset returns;
- overall and category inflation;
- income and capital-return split;
- deterministic seed behaviour;
- generator tests.

Suggested commit:

```text
feat(simulate): add stochastic return and inflation generator
```

### Stage 4: Vectorized simulation and summaries

Deliver:

- efficient multi-path execution;
- chunking where appropriate;
- summary statistics;
- percentile trajectories;
- failure summaries;
- sampled representative paths;
- performance checks.

Suggested commit:

```text
feat(simulate): add vectorized simulation and result summaries
```

### Stage 5: Persistence and reproducibility

Deliver:

- run directories;
- configuration and metadata persistence;
- summary Parquet files;
- cache policy;
- run loading and deletion;
- version and Git metadata.

Suggested commit:

```text
feat(simulate): persist reproducible simulation runs
```

### Stage 6: Web configuration workflow

Deliver:

- configuration pages;
- validation;
- run form;
- saved configuration views;
- Bootstrap integration;
- existing CSV grid/viewer integration.

Suggested commit:

```text
feat(simulate): add simulation configuration web workflow
```

### Stage 7: Results website and charts

Deliver:

- results summary;
- funnel chart;
- terminal wealth distribution;
- failure-date visualization;
- representative paths;
- saved-run list;
- comparison view.

Suggested commit:

```text
feat(simulate): add retirement simulation results dashboard
```

### Stage 8: Sequence-risk prototype

Deliver a small, clearly isolated prototype for:

- fixing one generated return environment;
- permuting its order;
- rerunning the cash-flow engine;
- estimating conditional failure rates;
- reporting order sensitivity.

Do not allow this stage to destabilize the main engine.

Suggested commit:

```text
feat(simulate): add conditional sequence-risk analysis
```

## 25. V1 completion criteria

V1 is complete when a user can:

1. configure a two-person household;
2. enter total annual real spending and a fixed category mix;
3. configure category inflation assumptions;
4. enter taxable, tax-deferred and tax-free balances by asset class;
5. configure a simple stochastic return generator;
6. enter state pension or Social Security-style income;
7. enter flat tax rates by income type;
8. run a reproducible quarterly simulation over 40 years;
9. execute approximately 100,000 scenarios within reasonable local resources;
10. view success and failure measures;
11. view a net-worth funnel;
12. inspect tabular summaries;
13. save, reload, compare and delete runs;
14. reproduce a run from its saved configuration and seed;
15. understand from the UI which assumptions are simplified.

## 26. Explicit V1 exclusions

Do not implement the following in the initial vertical slice unless required to make the architecture coherent:

- mortality simulation;
- morbidity simulation;
- dynamic spending mix;
- spending cuts;
- utility valuation;
- detailed UK tax law;
- detailed US tax law;
- tax-optimized withdrawal sequencing;
- required minimum distributions;
- rebalancing;
- historical bootstrap;
- block bootstrap;
- jump diffusion;
- stochastic volatility;
- full scenario discovery;
- UMAP analysis;
- machine-learning variable importance;
- robust optimization;
- annuitization;
- long-term-care insurance;
- full persistence of all scenario-period data.

Document extension points for these features rather than partially implementing them.

## 27. Design principles

The implementation should remain:

- transparent;
- testable;
- reproducible;
- computationally efficient;
- modular;
- inspectable;
- conservative about disk usage;
- explicit about approximations.

Prefer a small number of well-defined abstractions over a large framework.

The simulation engine is the core asset. Flask pages, charts and persistence should sit around the engine without contaminating its numerical design.

The initial implementation should produce failures rather than smoothing them away. Adaptive spending and other mitigating actions belong in later versions.

The long-term purpose is not merely to report a Monte Carlo success percentage. `fiscus_simulate` should evolve into a system that explains:

- which futures cause failure;
- whether failure is caused by inadequate aggregate returns or their ordering;
- how inflation and spending composition contribute;
- which assumptions matter;
- which adaptive decisions enlarge the safe region;
- how conclusions change under alternative models.
