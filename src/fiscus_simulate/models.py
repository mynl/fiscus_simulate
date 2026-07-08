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

SCHEMA_VERSION = "1.2"

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
    tax = "tax"


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
    """The ``account_type x asset_class -> initial balance`` matrix, plus taxable basis.

    ``taxable_basis`` is the initial cost basis of the **taxable** account's holdings, so
    a sale can be split into gain vs. return of principal. Only the taxable account needs
    it (tax-deferred is taxed on full withdrawal; tax-free is never taxed). If omitted for
    an asset, basis defaults to market value (no embedded gain). ``cash`` never has a gain.
    """

    balances: dict[AccountType, dict[AssetClass, float]]
    taxable_basis: dict[AssetClass, float] | None = None

    @field_validator("balances")
    @classmethod
    def _complete_and_non_negative(
        cls, v: dict[AccountType, dict[AssetClass, float]]
    ) -> dict[AccountType, dict[AssetClass, float]]:
        missing_acct = set(ACCOUNT_TYPES) - set(v)
        if missing_acct:
            raise ValueError(f"balances missing account types: {sorted(a.value for a in missing_acct)}")
        for acct, row in v.items():
            missing_asset = set(ASSET_CLASSES) - set(row)
            if missing_asset:
                raise ValueError(
                    f"balances[{acct.value}] missing asset classes: "
                    f"{sorted(a.value for a in missing_asset)}"
                )
            for asset, bal in row.items():
                if bal < 0:
                    raise ValueError(f"balance {acct.value}/{asset.value} is negative: {bal}")
        return v

    @model_validator(mode="after")
    def _basis_within_market(self) -> AccountBalances:
        if self.taxable_basis is None:
            return self
        taxable = self.balances[AccountType.taxable]
        for asset, basis in self.taxable_basis.items():
            if basis < 0:
                raise ValueError(f"taxable_basis[{asset.value}] is negative: {basis}")
            if basis > taxable[asset] + 1e-6:
                raise ValueError(
                    f"taxable_basis[{asset.value}] {basis} exceeds market value {taxable[asset]}"
                )
        return self

    def resolved_taxable_basis(self) -> dict[AssetClass, float]:
        """Taxable-account basis by asset, defaulting missing entries to market value."""
        taxable = self.balances[AccountType.taxable]
        given = self.taxable_basis or {}
        return {asset: float(given.get(asset, taxable[asset])) for asset in ASSET_CLASSES}

    def total(self) -> float:
        """Aggregate balance across all account types and asset classes."""
        return sum(bal for row in self.balances.values() for bal in row.values())

    def by_account(self) -> dict[AccountType, float]:
        """Total balance by account type."""
        return {acct: sum(row.values()) for acct, row in self.balances.items()}

    def by_asset(self) -> dict[AssetClass, float]:
        """Total balance by asset class (aggregated over accounts)."""
        out = {asset: 0.0 for asset in ASSET_CLASSES}
        for row in self.balances.values():
            for asset, bal in row.items():
                out[asset] += bal
        return out


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
    """V1: proportional withdrawal across all account/asset cells. Slot for V2 ordering."""

    kind: str = "proportional"


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
                people=[
                    Person(name="A", current_age=60, retirement_age=67,
                           annual_real_savings=30_000, income_streams=[
                               IncomeStream(label="pension", annual_real=11_000, start_age=67)]),
                    Person(name="B", current_age=58, retirement_age=67,
                           annual_real_savings=25_000, income_streams=[
                               IncomeStream(label="pension", annual_real=9_000, start_age=67)]),
                ],
                start_date=date(2026, 3, 31),
                horizon_years=40,
            ),
            spending=SpendingPlan(
                total_annual_real=60_000,
                category_pct={
                    SpendingCategory.housing: 30,
                    SpendingCategory.core: 30,
                    SpendingCategory.non_core: 15,
                    SpendingCategory.travel: 10,
                    SpendingCategory.medical: 10,
                    SpendingCategory.tax: 5,
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
                    SpendingCategory.tax: 0.0,
                },
            ),
            balances=AccountBalances(
                balances={
                    AccountType.taxable: {
                        AssetClass.stocks: 300_000, AssetClass.bonds: 100_000,
                        AssetClass.cash: 50_000},
                    AccountType.tax_deferred: {
                        AssetClass.stocks: 400_000, AssetClass.bonds: 200_000,
                        AssetClass.cash: 0},
                    AccountType.tax_free: {
                        AssetClass.stocks: 150_000, AssetClass.bonds: 50_000,
                        AssetClass.cash: 0},
                },
                # Embedded gains in the taxable account so example runs exercise gains tax.
                taxable_basis={
                    AssetClass.stocks: 200_000, AssetClass.bonds: 90_000,
                    AssetClass.cash: 50_000},
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
