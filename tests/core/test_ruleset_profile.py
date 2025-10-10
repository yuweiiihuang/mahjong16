from __future__ import annotations

from core.ruleset import Ruleset, load_rule_profile


def test_ruleset_loads_common_profile_defaults() -> None:
    profile = load_rule_profile("common")
    assert profile["include_flowers"] is True
    assert profile["dead_wall_mode"] == "fixed"
    assert profile["dead_wall_base"] == 16
    assert profile["randomize_seating_and_dealer"] is True
    assert profile["enable_wind_flower_scoring"] is True
    assert profile["enable_flower_wins"] is True
    assert profile["scoring_overrides_path"] is None

    rules = Ruleset()
    assert rules.rule_profile == "common"
    assert rules.include_flowers is True
    assert rules.dead_wall_mode == "fixed"
    assert rules.dead_wall_base == 16
    assert rules.randomize_seating_and_dealer is True
    assert rules.enable_wind_flower_scoring is True
    assert rules.enable_flower_wins is True
    assert rules.scoring_overrides_path is None


def test_ruleset_overrides_profile_values() -> None:
    rules = Ruleset(
        include_flowers=False,
        dead_wall_mode="gang_plus_one",
        dead_wall_base=20,
        randomize_seating_and_dealer=True,
        enable_wind_flower_scoring=False,
        enable_flower_wins=False,
    )
    assert rules.include_flowers is False
    assert rules.dead_wall_mode == "gang_plus_one"
    assert rules.dead_wall_base == 20
    assert rules.randomize_seating_and_dealer is True
    assert rules.enable_wind_flower_scoring is False
    assert rules.enable_flower_wins is False
