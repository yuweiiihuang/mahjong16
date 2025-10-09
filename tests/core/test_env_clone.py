"""Tests for cloning the Mahjong16 environment state."""

from core import Mahjong16Env, Ruleset


def _pass_all_reactions(env: Mahjong16Env) -> None:
    """Advance through the current reaction window by passing."""

    while env.phase == "REACTION" and not env.done:
        env.step({"type": "PASS"})


def test_clone_preserves_and_isolates_state() -> None:
    rules = Ruleset(include_flowers=False)
    env = Mahjong16Env(rules, seed=7)

    env.reset()

    initial_discard = next(a for a in env.legal_actions() if a["type"] == "DISCARD")
    env.step(initial_discard)
    _pass_all_reactions(env)

    assert env.phase == "TURN"

    acting_pid = env.turn
    clone = env.clone()

    pre_clone_wall = list(clone.wall)

    env_discards = [a for a in env.legal_actions() if a["type"] == "DISCARD"]
    clone_discards = [a for a in clone.legal_actions() if a["type"] == "DISCARD"]

    assert env_discards, "environment should have at least one discard choice"
    assert len(clone_discards) >= 2, "clone should expose multiple discard branches"

    env_wall_len_before = len(env.wall)

    env.step(env_discards[0])
    _pass_all_reactions(env)

    assert list(clone.wall) == pre_clone_wall, "mutating env should not touch clone wall"

    clone.step(clone_discards[1])

    assert env.players[acting_pid].river != clone.players[acting_pid].river
    assert env.phase != clone.phase
    assert env.legal_actions() != clone.legal_actions()
    assert len(env.wall) < len(clone.wall)
    assert len(env.wall) == env_wall_len_before - 1
