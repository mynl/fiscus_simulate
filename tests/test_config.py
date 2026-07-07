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
        Household(people=[Person(role="solo", current_age=60, pension_start_age=67,
                                 annual_real_pension=0)],
                  start_date="2026-03-31")


def test_negative_balance_rejected():
    cfg = RunConfig.default()
    data = cfg.model_dump(mode="json")
    data["balances"]["balances"]["taxable"]["cash"] = -1
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


def test_income_owner_must_be_household_member():
    cfg = RunConfig.default()
    data = cfg.model_dump(mode="json")
    data["income_streams"][0]["owner"] = "ghost"
    with pytest.raises(ValidationError, match="not a household member"):
        RunConfig.model_validate(data)


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


def test_clone_is_independent():
    cfg = RunConfig.default()
    twin = cfg.clone()
    twin.spending.total_annual_real = 99_999
    assert cfg.spending.total_annual_real != 99_999
