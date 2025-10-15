"""Tests focused on seat assignment and dealer selection logic during reset."""

from domain import Mahjong16Env
from domain.rules import Ruleset


def test_randomized_seating_changes_over_resets():
    """Randomized seating should produce multiple seat permutations and matching dealer."""
    env = Mahjong16Env(Ruleset(randomize_seating_and_dealer=True), seed=5)

    seen_orders = set()
    for _ in range(3):
        env.reset()
        seen_orders.add(tuple(env.seating_order))
        assert sorted(env.seating_order) == list(range(env.rules.n_players))
        expected_dealer = env.seat_winds.index("E")
        assert env.dealer_pid == expected_dealer

    assert len(seen_orders) > 1, "Randomized seating should not stay fixed across resets"


def test_preset_overrides_bypass_randomization():
    """Preset winds, dealer, and round metadata should override randomization switches."""
    rules = Ruleset(randomize_seating_and_dealer=True)
    env = Mahjong16Env(rules, seed=17)
    env.preset_seat_winds = ["W", "N", "E", "S"]
    env.preset_dealer_pid = 2
    env.preset_quan_feng = "S"
    env.preset_dealer_streak = 3

    env.reset()

    assert env.seat_winds == ["W", "N", "E", "S"]
    assert env.seating_order == [2, 3, 0, 1]
    assert env.dealer_pid == 2
    assert env.turn == 2
    assert env.quan_feng == "S"
    assert env.dealer_streak == 3
