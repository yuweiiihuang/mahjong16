"""Integration tests that exercise the public :mod:`domain` API surface."""
from __future__ import annotations

from domain import Mahjong16Env
from domain.analysis import (
    simulate_after_discard,
    visible_count_after,
    visible_count_global,
)
from domain.rules import Ruleset
from domain.tiles import tile_to_str


def test_domain_env_reset_produces_turn_observation() -> None:
    rules = Ruleset(randomize_seating_and_dealer=False, include_flowers=False)
    env = Mahjong16Env(rules, seed=0)
    obs = env.reset()
    assert obs["phase"] == "TURN"
    assert len(obs["hand"]) == rules.initial_hand


def test_domain_tile_helpers_behave_consistently() -> None:
    assert tile_to_str(0) == "1W"
    assert tile_to_str(33) == "P"


def test_domain_analysis_helpers_operate_on_observations() -> None:
    hand_after = simulate_after_discard([0, 1, 2], drawn=3, tile=2, source="hand")
    assert sorted(hand_after) == [0, 1, 3]

    obs = {
        "hand": [0, 1],
        "melds_all": [[{"tiles": [0, 0, 0]}]],
        "rivers": [[0], [0, 2]],
    }
    assert visible_count_global(0, obs) == 6
    assert visible_count_after(0, hand_after, obs) == 6
