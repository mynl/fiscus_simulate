"""Typed configuration models for a simulation run.

The :class:`RunConfig` tree is the single source of truth for a run: every later
stage (engine, generators, persistence, web) consumes it. Models are pydantic v2 with
``extra="forbid"`` so typos in a hand-edited YAML file are caught rather than ignored.

Canonical orderings (spending categories, asset classes, account types) are defined
here once, via enum member order, and reused everywhere — never redefined per view.

Notes
-----
V1 is deliberately small (see ``dev/plan-overview.md``): inflation is constant
(deterministic), so the spending liability is a single path shared by all scenarios,
and the only stochastic driver is asset returns. Fields that will carry stochastic
inflation in V2 (volatilities, correlations) exist here but default to zero and are
ignored by the V1 engine. The shape is fixed now so nothing re-architects later.
"""
from __future__ import annotations

import math
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.3"

# Numerical tolerance for the spending category-percentage sum check.
PCT_SUM_TOL = 1e-6


# --------------------------------------------------------------------------- enums
class SpendingCategory(str, Enum):
    """Household spending categories (V1 fixed mix). Enum order is canonical."""

    housing = "housing"
    core = "core"
    non_core = "non_core"
    travel = "travel"
    medical = "medical"


class AssetClass(str, Enum):
    """Asset classes (V1). Enum order is canonical and drives correlation ordering."""

    stocks = "stocks"
    bonds = "bonds"
    cash = "cash"


class AccountType(str, Enum):
    """Account tax treatments (V1). Enum order is canonical."""

    taxable = "taxable"
    tax_deferred = "tax_deferred"
    tax_free = "tax_free"


class QuarterConvention(str, Enum):
    """Quarter-end date convention. V1 uses calendar quarter-ends (see initial_ask §5)."""

    calendar_qend = "calendar_qend"


SPENDING_CATEGORIES: tuple[SpendingCategory, ...] = tuple(SpendingCategory)
ASSET_CLASSES: tuple[AssetClass, ...] = tuple(AssetClass)
ACCOUNT_TYPES: tuple[AccountType, ...] = tuple(AccountType)


class _Model(BaseModel):
    """Base model: forbid unknown fields so hand-edited configs fail loudly on typos."""

    model_config = ConfigDict(extra="forbid")


# ----------------------------------------------------------------------- household
class IncomeStream(_Model):
    """An external income stream owned by a person (state pension / Social Security).

    Streams are nested under their owning :class:`Person` (V1.1) — the person *is* the
    owner, so there is no separate owner key to keep in sync. A stream is active while
    the owner's age is in ``[start_age, end_age)``.

    Parameters
    ----------
    label : str
        Human-readable descriptor, e.g. ``"state pension"`` or ``"Social Security"``.
    annual_real : float
        Annual real (today's-money) amount once started.
    start_age : float
        Owner age at which the income begins.
    end_age : float or None
        Optional owner age at which it stops (``None`` = runs to horizon end).
    inflation_linked : bool
        If True the amount grows with overall inflation; otherwise fixed in nominal
        terms (eroding in real terms).
    taxable_fraction : float
        Portion of the income subject to the ``other_pension`` tax rate.
    """

    label: str = "pension"
    annual_real: float = Field(ge=0)
    start_age: float = Field(ge=0, lt=120)
    end_age: float | None = Field(default=None, ge=0, le=120)
    inflation_linked: bool = True
    taxable_fraction: float = Field(default=1.0, ge=0, le=1)


class Person(_Model):
    """One household member: current age, retirement, savings, and income streams.

    Parameters
    ----------
    name : str
        The person's name (or a short label like ``"A"``). Used for display.
    current_age : float
        Age in years at the simulation start date.
    retirement_age : float or None
        Age at which the person stops working and saving. ``None`` means "already
        retired" — no accumulation phase (spending can begin at period 0).
    annual_real_savings : float
        Real (today's-money) amount saved into the pooled portfolio each year while
        ``current_age <= age < retirement_age``. Ignored once retired.
    income_streams : list of IncomeStream
        Pensions / Social-Security-style income belonging to this person (may be empty).

    Notes
    -----
    Pre-retirement, the household is assumed to cover living costs from salary, so only
    the *net* saving is modeled (see ``savings.py`` / the engine order of operations).
    """

    name: str
    current_age: float = Field(gt=0, lt=120)
    retirement_age: float | None = Field(default=None, ge=0, le=120)
    annual_real_savings: float = Field(default=0.0, ge=0)
    income_streams: list[IncomeStream] = Field(default_factory=list)

    def retirement_period(self) -> int:
        """Period index at which this person retires (0 if already retired / unset)."""
        if self.retirement_age is None or self.retirement_age <= self.current_age:
            return 0
        return math.ceil((self.retirement_age - self.current_age) * 4)


class Household(_Model):
    """A two-person household over a fixed horizon (no mortality in V1)."""

    people: list[Person]
    start_date: date
    horizon_years: int = Field(default=40, gt=0, le=100)
    quarter_convention: QuarterConvention = QuarterConvention.calendar_qend

    @field_validator("people")
    @classmethod
    def _exactly_two(cls, v: list[Person]) -> list[Person]:
        if len(v) != 2:
            raise ValueError(f"household must contain exactly two people, got {len(v)}")
        return v

    @property
    def n_periods(self) -> int:
        """Number of quarterly periods over the horizon."""
        return self.horizon_years * 4

    @property
    def spending_start_period(self) -> int:
        """Period at which household spending (drawdown) begins.

        Notes
        -----
        The household is "fully retired" — and so begins its retirement spending — when
        the **last** person retires. Before that, a still-working spouse's salary is
        assumed to cover living costs, so only net saving is modeled and no drawdown
        occurs. Clamped to the horizon.
        """
        latest = max((p.retirement_period() for p in self.people), default=0)
        return min(latest, self.n_periods)


# ------------------------------------------------------------------------ spending
class SpendingPlan(_Model):
    """Total annual real spending plus a fixed percentage mix across categories.

    Notes
    -----
    V1 supports only "stick to planned spending": the mix is fixed over the horizon
    and expenditure does not fall when assets are strained — failure is exposed, not
    smoothed away.
    """

    total_annual_real: float = Field(ge=0)
    category_pct: dict[SpendingCategory, float]
    mode: str = "planned"  # V1: the only mode; V2 adds adaptive rules.

    @field_validator("category_pct")
    @classmethod
    def _complete_and_sum_100(
        cls, v: dict[SpendingCategory, float]
    ) -> dict[SpendingCategory, float]:
        missing = set(SPENDING_CATEGORIES) - set(v)
        if missing:
            raise ValueError(f"category_pct missing categories: {sorted(m.value for m in missing)}")
        total = sum(v.values())
        if abs(total - 100.0) > PCT_SUM_TOL * 100:
            raise ValueError(f"category percentages must sum to 100, got {total}")
        return v


class InflationAssumptions(_Model):
    """Overall and per-category inflation.

    Notes
    -----
    Category inflation follows ``pi_k = pi + delta_k`` (overall plus category excess).
    **V1 uses the means only (deterministic, constant over time)** → one shared nominal
    spending path. The ``*_vol`` fields are the V2 stochastic seam and are ignored by
    the V1 engine.
    """

    overall_mean: float
    overall_vol: float = Field(default=0.0, ge=0)
    category_excess_mean: dict[SpendingCategory, float]
    category_excess_vol: dict[SpendingCategory, float] | None = None

    @field_validator("category_excess_mean")
    @classmethod
    def _complete_excess(cls, v: dict[SpendingCategory, float]) -> dict[SpendingCategory, float]:
        missing = set(SPENDING_CATEGORIES) - set(v)
        if missing:
            raise ValueError(
                f"category_excess_mean missing: {sorted(m.value for m in missing)}"
            )
        return v


# -------------------------------------------------------------------------- assets
class AccountBalances(_Model):
    """Whole-portfolio asset totals in dollars; tax-treatment split and basis as fractions.

    Only ``totals`` is in dollars — the amount of each asset class across the whole
    household. ``tax_deferred_proportion`` and ``tax_free_proportion`` are the fraction of
    each asset-class total held in those account types; the **taxable** account is the
    implied remainder. ``taxable_basis_proportion`` is the cost basis as a fraction of that
    implied taxable holding (so a sale splits into gain vs. return of principal).

    This anchors one dollar figure per asset class and keeps the composition fixed when the
    totals are rescaled.

    Notes
    -----
    All proportions are **fractions in [0, 1]** (NOT percentages). Per asset,
    ``tax_deferred_proportion + tax_free_proportion <= 1`` so the taxable remainder is
    non-negative. ``cash`` typically sits wholly in the taxable account with basis 1.0
    (no embedded gain).
    """

    totals: dict[AssetClass, float]
    tax_deferred_proportion: dict[AssetClass, float]
    tax_free_proportion: dict[AssetClass, float]
    taxable_basis_proportion: dict[AssetClass, float]

    @field_validator("totals", "tax_deferred_proportion", "tax_free_proportion",
                     "taxable_basis_proportion")
    @classmethod
    def _complete_assets(cls, v: dict[AssetClass, float]) -> dict[AssetClass, float]:
        missing = set(ASSET_CLASSES) - set(v)
        if missing:
            raise ValueError(f"missing asset classes: {sorted(a.value for a in missing)}")
        return v

    @field_validator("totals")
    @classmethod
    def _totals_non_negative(cls, v: dict[AssetClass, float]) -> dict[AssetClass, float]:
        for asset, amount in v.items():
            if amount < 0:
                raise ValueError(f"totals[{asset.value}] is negative: {amount}")
        return v

    @field_validator("tax_deferred_proportion", "tax_free_proportion",
                     "taxable_basis_proportion")
    @classmethod
    def _fraction_range(cls, v: dict[AssetClass, float]) -> dict[AssetClass, float]:
        for asset, x in v.items():
            if not 0.0 <= x <= 1.0:
                raise ValueError(f"proportion for {asset.value} out of [0, 1]: {x}")
        return v

    @model_validator(mode="after")
    def _taxable_remainder_non_negative(self) -> AccountBalances:
        for asset in ASSET_CLASSES:
            share = self.tax_deferred_proportion[asset] + self.tax_free_proportion[asset]
            if share > 1.0 + 1e-9:
                raise ValueError(
                    f"tax_deferred_proportion + tax_free_proportion for {asset.value} "
                    f"exceeds 1 (taxable would be negative): {share}"
                )
        return self

    def amounts(self) -> dict[AccountType, dict[AssetClass, float]]:
        """Reconstruct the ``account_type x asset_class`` dollar matrix (taxable = remainder)."""
        out: dict[AccountType, dict[AssetClass, float]] = {acct: {} for acct in ACCOUNT_TYPES}
        for asset in ASSET_CLASSES:
            total = self.totals[asset]
            td = total * self.tax_deferred_proportion[asset]
            tf = total * self.tax_free_proportion[asset]
            out[AccountType.tax_deferred][asset] = td
            out[AccountType.tax_free][asset] = tf
            out[AccountType.taxable][asset] = total - td - tf
        return out

    def resolved_taxable_basis(self) -> dict[AssetClass, float]:
        """Taxable cost basis by asset: implied taxable holding x basis fraction."""
        taxable = self.amounts()[AccountType.taxable]
        return {a: float(taxable[a] * self.taxable_basis_proportion[a]) for a in ASSET_CLASSES}

    def total(self) -> float:
        """Aggregate household wealth across all asset classes."""
        return float(sum(self.totals.values()))

    def by_account(self) -> dict[AccountType, float]:
        """Total balance by account type."""
        return {acct: sum(row.values()) for acct, row in self.amounts().items()}

    def by_asset(self) -> dict[AssetClass, float]:
        """Total balance by asset class (= the totals)."""
        return {a: float(self.totals[a]) for a in ASSET_CLASSES}


# ------------------------------------------------------------------------- returns
class ReturnGeneratorConfig(_Model):
    """Parameters for the V1 correlated GBM/lognormal return generator (Stage 3).

    Real expected returns are the primary parameterization; nominal is derived as
    ``1 + R_nominal = (1 + r_real)(1 + pi)`` (see initial_ask §9.2). ``correlations``
    is a matrix in :data:`ASSET_CLASSES` order.
    """

    kind: str = "gbm"
    real_return: dict[AssetClass, float]
    volatility: dict[AssetClass, float]
    income_yield: dict[AssetClass, float]
    correlations: list[list[float]]

    @field_validator("real_return", "volatility", "income_yield")
    @classmethod
    def _complete_assets(cls, v: dict[AssetClass, float]) -> dict[AssetClass, float]:
        missing = set(ASSET_CLASSES) - set(v)
        if missing:
            raise ValueError(f"missing asset classes: {sorted(a.value for a in missing)}")
        return v

    @field_validator("volatility")
    @classmethod
    def _vol_non_negative(cls, v: dict[AssetClass, float]) -> dict[AssetClass, float]:
        for asset, vol in v.items():
            if vol < 0:
                raise ValueError(f"volatility[{asset.value}] is negative: {vol}")
        return v

    @field_validator("correlations")
    @classmethod
    def _valid_correlation_matrix(cls, v: list[list[float]]) -> list[list[float]]:
        n = len(ASSET_CLASSES)
        if len(v) != n or any(len(row) != n for row in v):
            raise ValueError(f"correlations must be {n}x{n} (asset order {ASSET_CLASSES})")
        for i in range(n):
            if abs(v[i][i] - 1.0) > 1e-9:
                raise ValueError("correlation matrix diagonal must be 1")
            for j in range(n):
                if not -1.0 <= v[i][j] <= 1.0:
                    raise ValueError(f"correlation[{i}][{j}] out of [-1, 1]: {v[i][j]}")
                if abs(v[i][j] - v[j][i]) > 1e-9:
                    raise ValueError("correlation matrix must be symmetric")
        return v


# ----------------------------------------------------------------------------- tax
class TaxRates(_Model):
    """Flat marginal tax rates by income type (V1 simplification).

    Notes
    -----
    Tax-free account withdrawals are implicitly zero-rated. This is a deliberately
    simplified approximation and is labelled as such in the UI/output.
    """

    tax_deferred_withdrawal: float = Field(ge=0, le=1)
    interest: float = Field(ge=0, le=1)
    dividend: float = Field(ge=0, le=1)
    realized_gain: float = Field(ge=0, le=1)
    other_pension: float = Field(ge=0, le=1)


# ------------------------------------------------------------------ policies / sim
class WithdrawalPolicy(_Model):
    """How assets are liquidated to fund a shortfall, plus RMD settings.

    ``kind`` selects the sale strategy: ``"proportional"`` (across all account/asset cells
    at once) or ``"ordered"`` (drain accounts in ``order``, tax-efficient). ``order`` is the
    account draw-down priority for the ordered strategy. RMDs force a minimum tax-deferred
    withdrawal once the eldest person reaches ``rmd_start_age`` (see :mod:`.rmd`).

    Notes
    -----
    The ordered strategy and RMDs are consumed by the re-timed engine (1.9.0 integration);
    the field defaults describe the intended behavior.
    """

    kind: str = "ordered"  # "ordered" (taxable→tax-deferred→tax-free) | "proportional"
    order: list[AccountType] = Field(default_factory=lambda: list(ACCOUNT_TYPES))
    rmd_enabled: bool = True
    rmd_start_age: float = Field(default=75, ge=0, le=120)

    @field_validator("order")
    @classmethod
    def _order_is_permutation(cls, v: list[AccountType]) -> list[AccountType]:
        if set(v) != set(ACCOUNT_TYPES) or len(v) != len(ACCOUNT_TYPES):
            raise ValueError(
                f"withdrawal order must be a permutation of {[a.value for a in ACCOUNT_TYPES]}"
            )
        return v


class RebalancingPolicy(_Model):
    """V1: no rebalancing (weights drift with returns/withdrawals). Slot for V2 policy."""

    kind: str = "none"


class SimulationConfig(_Model):
    """Run-scale and reproducibility controls."""

    n_scenarios: int = Field(default=10_000, gt=0)
    seed: int = 12345
    chunk_size: int = Field(default=10_000, gt=0)
    terminal_threshold: float = Field(default=0.0, ge=0)  # success criterion 4 floor
    persist_summary: bool = True
    persist_sample_paths: int = Field(default=0, ge=0)  # optional bounded path sample


# -------------------------------------------------------------------- top-level cfg
class RunConfig(_Model):
    """Complete configuration for one simulation run (the single source of truth)."""

    schema_version: str = SCHEMA_VERSION
    household: Household
    spending: SpendingPlan
    inflation: InflationAssumptions
    balances: AccountBalances
    return_generator: ReturnGeneratorConfig
    tax_rates: TaxRates
    withdrawal_policy: WithdrawalPolicy = Field(default_factory=WithdrawalPolicy)
    rebalancing_policy: RebalancingPolicy = Field(default_factory=RebalancingPolicy)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)

    def clone(self) -> RunConfig:
        """Return a deep copy (basis for a new, independently-editable run)."""
        return self.model_copy(deep=True)

    @classmethod
    def default(cls) -> RunConfig:
        """Construct a valid, illustrative two-person example configuration.

        Notes
        -----
        Figures are synthetic and for smoke-testing only — not advice, not real data.
        """
        return cls(
            household=Household(
                # A retired two-person household. Both retired at 62 (spending starts at
                # period 0, no accumulation); A has Social Security starting at 67, B none.
                people=[
                    Person(name="A", current_age=62, retirement_age=62,
                           annual_real_savings=0, income_streams=[
                               IncomeStream(label="Social Security", annual_real=40_000,
                                            start_age=67)]),
                    Person(name="B", current_age=62, retirement_age=62,
                           annual_real_savings=0, income_streams=[]),
                ],
                start_date=date(2026, 3, 31),
                horizon_years=40,
            ),
            spending=SpendingPlan(
                total_annual_real=60_000,
                # Tax is computed from income and gains (not a budget line), so no "tax"
                # category. The remaining five sum to 100.
                category_pct={
                    SpendingCategory.housing: 32,
                    SpendingCategory.core: 32,
                    SpendingCategory.non_core: 16,
                    SpendingCategory.travel: 10,
                    SpendingCategory.medical: 10,
                },
            ),
            inflation=InflationAssumptions(
                overall_mean=0.025,
                category_excess_mean={
                    SpendingCategory.housing: 0.0,
                    SpendingCategory.core: 0.0,
                    SpendingCategory.non_core: 0.0,
                    SpendingCategory.travel: 0.0,
                    SpendingCategory.medical: 0.02,
                },
            ),
            balances=AccountBalances(
                # Whole-portfolio dollars per asset class (total 1,250,000).
                totals={AssetClass.stocks: 850_000, AssetClass.bonds: 350_000,
                        AssetClass.cash: 50_000},
                # Fractions (0-1) of each asset-class total by tax treatment; taxable is
                # the implied remainder (stocks 0.30, bonds 0.35, cash 1.00).
                tax_deferred_proportion={AssetClass.stocks: 0.5, AssetClass.bonds: 0.5,
                                         AssetClass.cash: 0.0},
                tax_free_proportion={AssetClass.stocks: 0.2, AssetClass.bonds: 0.15,
                                     AssetClass.cash: 0.0},
                # Basis as a fraction of the implied taxable holding (embedded gains for
                # stocks/bonds so example runs exercise the gains tax).
                taxable_basis_proportion={AssetClass.stocks: 0.7, AssetClass.bonds: 0.9,
                                          AssetClass.cash: 1.0},
            ),
            return_generator=ReturnGeneratorConfig(
                real_return={AssetClass.stocks: 0.05, AssetClass.bonds: 0.015,
                             AssetClass.cash: 0.0},
                volatility={AssetClass.stocks: 0.17, AssetClass.bonds: 0.06,
                            AssetClass.cash: 0.01},
                income_yield={AssetClass.stocks: 0.02, AssetClass.bonds: 0.03,
                              AssetClass.cash: 0.01},
                correlations=[[1.0, 0.2, 0.0], [0.2, 1.0, 0.1], [0.0, 0.1, 1.0]],
            ),
            tax_rates=TaxRates(
                tax_deferred_withdrawal=0.20, interest=0.20, dividend=0.15,
                realized_gain=0.15, other_pension=0.20,
            ),
        )

    @classmethod
    def generic(cls) -> RunConfig:
        """A fully-populated *accumulation-phase* demo (still saving toward retirement).

        Every optional field is exercised: two working people with savings rates and
        pensions, so the editor and the retirement projection have something to show for
        someone who is not yet retired. Synthetic figures — not advice, not real data.
        """
        cfg = cls.default()
        cfg.household.people = [
            Person(name="A", current_age=45, retirement_age=67, annual_real_savings=30_000,
                   income_streams=[IncomeStream(label="Social Security", annual_real=30_000,
                                                start_age=67)]),
            Person(name="B", current_age=43, retirement_age=65, annual_real_savings=25_000,
                   income_streams=[
                       IncomeStream(label="Social Security", annual_real=22_000, start_age=67),
                       IncomeStream(label="employer pension", annual_real=12_000, start_age=65,
                                    inflation_linked=False)]),
        ]
        # A smaller portfolio mid-accumulation (composition unchanged).
        cfg.balances.totals = {AssetClass.stocks: 340_000, AssetClass.bonds: 120_000,
                               AssetClass.cash: 40_000}
        return cfg
