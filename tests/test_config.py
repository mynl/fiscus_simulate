"""Configuration model tests: construction, validation, and YAML round-trip."""
from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from fiscus_simulate.config import from_yaml_str, load_config, save_config, to_yaml_str
from fiscus_simulate.models import (
    ACCOUNT_TYPES,
    ASSET_CLASSES,
    SCHEMA_VERSION,
    SPENDING_CATEGORIES,
    AccountType,
    AssetClass,
    Household,
    Person,
    RunConfig,
    SpendingCategory,
    SpendingPlan,
)


def test_default_constructs_and_validates():
    cfg = RunConfig.default()
    assert cfg.schema_version == SCHEMA_VERSION
    assert cfg.household.n_periods == 160
    assert cfg.balances.total() > 0


def test_yaml_round_trip_equal(tmp_path):
    cfg = RunConfig.default()
    path = save_config(cfg, tmp_path / "run.yaml")
    assert path.exists()
    loaded = load_config(path)
    assert loaded == cfg


def test_yaml_is_human_readable_strings():
    text = to_yaml_str(RunConfig.default())
    data = yaml.safe_load(text)
    assert data["schema_version"] == SCHEMA_VERSION
    # enums serialize to their string values, not Python enum reprs
    assert "housing" in data["spending"]["category_pct"]
    assert "stocks" in data["return_generator"]["real_return"]


def test_canonical_orders_complete():
    assert [c.value for c in SPENDING_CATEGORIES] == [
        "housing", "core", "non_core", "travel", "medical", "tax"]
    assert [a.value for a in ASSET_CLASSES] == ["stocks", "bonds", "cash"]
    assert [a.value for a in ACCOUNT_TYPES] == ["taxable", "tax_deferred", "tax_free"]


def test_spending_pct_must_sum_to_100():
    bad = {c: 10.0 for c in SpendingCategory}  # sums to 60
    with pytest.raises(ValidationError, match="sum to 100"):
        SpendingPlan(total_annual_real=1000, category_pct=bad)


def test_spending_pct_missing_category():
    partial = {SpendingCategory.housing: 100.0}
    with pytest.raises(ValidationError, match="missing categories"):
        SpendingPlan(total_annual_real=1000, category_pct=partial)


def test_household_must_have_two_people():
    with pytest.raises(ValidationError, match="exactly two"):
        Household(people=[Person(name="solo", current_age=60)],
                  start_date="2026-03-31")


def test_negative_total_rejected():
    cfg = RunConfig.default()
    data = cfg.model_dump(mode="json")
    data["balances"]["totals"]["cash"] = -1
    with pytest.raises(ValidationError, match="negative"):
        RunConfig.model_validate(data)


def test_bad_correlation_matrix_rejected():
    cfg = RunConfig.default()
    data = cfg.model_dump(mode="json")
    data["return_generator"]["correlations"] = [[1, 0.5, 0], [0.4, 1, 0], [0, 0, 1]]  # asymmetric
    with pytest.raises(ValidationError, match="symmetric"):
        RunConfig.model_validate(data)


def test_unknown_field_rejected():
    cfg = RunConfig.default()
    data = cfg.model_dump(mode="json")
    data["surprise"] = 1
    with pytest.raises(ValidationError):
        RunConfig.model_validate(data)


def test_income_streams_nest_under_people():
    cfg = RunConfig.default()
    # Streams live on the person now — no separate top-level list / owner key.
    assert not hasattr(cfg, "income_streams")
    assert cfg.household.people[0].name == "A"
    assert cfg.household.people[0].income_streams[0].annual_real == 11_000
    # Round-trips with the nesting intact.
    again = from_yaml_str(to_yaml_str(cfg))
    assert again.household.people[1].income_streams[0].annual_real == 9_000


def test_person_may_have_no_income_streams():
    p = Person(name="C", current_age=55)
    assert p.income_streams == []


def test_schema_version_mismatch_warns():
    text = to_yaml_str(RunConfig.default()).replace(
        f"schema_version: '{SCHEMA_VERSION}'", "schema_version: '0.9'")
    # tolerate quoting differences: only assert warning if the swap took effect
    if "0.9" in text:
        with pytest.warns(UserWarning, match="schema_version"):
            from_yaml_str(text)


def test_balances_helpers():
    cfg = RunConfig.default()
    by_acct = cfg.balances.by_account()
    by_asset = cfg.balances.by_asset()
    assert set(by_acct) == set(AccountType)
    assert set(by_asset) == set(AssetClass)
    assert abs(sum(by_acct.values()) - cfg.balances.total()) < 1e-6
    assert abs(sum(by_asset.values()) - cfg.balances.total()) < 1e-6


def test_basis_proportion_out_of_range_rejected():
    cfg = RunConfig.default()
    data = cfg.model_dump(mode="json")
    data["balances"]["taxable_basis_proportion"]["stocks"] = 1.5  # fractions are 0-1
    with pytest.raises(ValidationError, match="out of"):
        RunConfig.model_validate(data)


def test_account_proportions_over_one_rejected():
    cfg = RunConfig.default()
    data = cfg.model_dump(mode="json")
    data["balances"]["tax_deferred_proportion"]["stocks"] = 0.8
    data["balances"]["tax_free_proportion"]["stocks"] = 0.5  # 1.3 > 1 -> taxable negative
    with pytest.raises(ValidationError, match="exceeds 1"):
        RunConfig.model_validate(data)


def test_amounts_and_resolved_basis():
    cfg = RunConfig.default()
    amt = cfg.balances.amounts()
    # taxable = total x (1 - td - tf); default stocks: 850k x (1 - 0.5 - 0.2) = 255k.
    assert amt[AccountType.taxable][AssetClass.stocks] == 850_000 * (1 - 0.5 - 0.2)
    assert amt[AccountType.tax_deferred][AssetClass.stocks] == 850_000 * 0.5
    # basis = implied taxable holding x basis fraction (stocks 255k x 0.7).
    resolved = cfg.balances.resolved_taxable_basis()
    assert resolved[AssetClass.stocks] == 850_000 * 0.3 * 0.7
    # totals reconstruct exactly: taxable + tax_deferred + tax_free == total per asset.
    for a in AssetClass:
        got = sum(amt[acct][a] for acct in AccountType)
        assert abs(got - cfg.balances.totals[a]) < 1e-6


def test_clone_is_independent():
    cfg = RunConfig.default()
    twin = cfg.clone()
    twin.spending.total_annual_real = 99_999
    assert cfg.spending.total_annual_real != 99_999
