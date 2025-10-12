"""Integration tests ensuring the deprecated :mod:`core` facade still works."""
from __future__ import annotations

import core
from core.tiles import tile_to_str
from domain import Mahjong16Env as DomainEnv
from domain.rules import Ruleset


def test_core_env_alias_matches_domain() -> None:
    assert core.Mahjong16Env is DomainEnv
    rules = Ruleset(randomize_seating_and_dealer=False, include_flowers=False)
    env = core.Mahjong16Env(rules, seed=0)
    obs = env.reset()
    assert obs["phase"] == "TURN"
    assert len(obs["hand"]) == rules.initial_hand


def test_core_tile_helpers_still_accessible() -> None:
    assert tile_to_str(0) == "1W"
    assert tile_to_str(33) == "P"
