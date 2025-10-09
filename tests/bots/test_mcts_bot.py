"""Regression tests for the Monte Carlo Tree Search bot."""

from __future__ import annotations

from typing import Iterable

import pytest

from bots import MCTSBot, MCTSBotConfig
from core import Mahjong16Env, Ruleset
from core.tiles import Tile


def _build_rules() -> Ruleset:
    return Ruleset(
        include_flowers=False,
        dead_wall_mode="fixed",
        dead_wall_base=16,
        scoring_profile="taiwan_base",
        see_flower_see_wind=False,
        randomize_seating_and_dealer=False,
        enable_wind_flower_scoring=False,
        scoring_overrides_path=None,
    )


def _action_types(actions: Iterable[dict]) -> set[str]:
    return {(action.get("type") or "").upper() for action in actions}


def test_mcts_bot_returns_legal_actions_during_turn():
    env = Mahjong16Env(_build_rules(), seed=7)
    bot = MCTSBot(env, MCTSBotConfig(simulations=6, rollout_depth=2, seed=0))

    obs = env.reset()
    for _ in range(12):
        actions = obs.get("legal_actions", [])
        assert actions, "environment must always provide legal actions"
        action = bot.choose(obs)
        assert action in actions
        obs, _reward, done, _info = env.step(action)
        if done:
            break


def test_mcts_bot_handles_reaction_candidates():
    env = Mahjong16Env(_build_rules(), seed=11)
    env.reset()

    env.phase = "REACTION"
    env.reaction_queue = [1, 2, 3]
    env.reaction_idx = 0
    env.last_discard = {"pid": 0, "tile": int(Tile.D6)}
    env.claims = []
    env.qiang_gang_mode = False
    env.done = False

    player = env.players[1]
    player.hand = [
        int(Tile.W1),
        int(Tile.W2),
        int(Tile.W3),
        int(Tile.W4),
        int(Tile.W5),
        int(Tile.W6),
        int(Tile.D4),
        int(Tile.D5),
        int(Tile.D6),
        int(Tile.D6),
        int(Tile.D6),
        int(Tile.D7),
        int(Tile.D8),
        int(Tile.D9),
        int(Tile.E),
        int(Tile.E),
    ]
    player.drawn = None
    player.melds = []
    player.declared_ting = False

    obs = env._obs(1)
    legal = obs.get("legal_actions", [])
    types = _action_types(legal)
    assert {"PASS", "CHI", "PONG", "HU"}.issubset(types)

    bot = MCTSBot(env, MCTSBotConfig(simulations=8, rollout_depth=2, seed=0))
    action = bot.choose(obs)
    assert action in legal


def test_mcts_rollout_heuristic_is_deterministic():
    rules = _build_rules()
    config = MCTSBotConfig(simulations=8, rollout_depth=2, seed=321)

    env = Mahjong16Env(rules, seed=5)
    obs = env.reset()
    bot = MCTSBot(env, config)

    value = bot._evaluate(env, obs["player"])
    assert value != 0.0

    first_action = bot.choose(obs)

    env_clone = Mahjong16Env(rules, seed=5)
    obs_clone = env_clone.reset()
    bot_clone = MCTSBot(env_clone, config)
    second_action = bot_clone.choose(obs_clone)

    assert second_action == first_action


def test_policy_prior_biases_winning_actions():
    env = Mahjong16Env(_build_rules(), seed=17)
    bot = MCTSBot(env, MCTSBotConfig(simulations=4, rollout_depth=1, seed=4))

    actions = [
        {"type": "PASS"},
        {"type": "PONG"},
        {"type": "HU"},
    ]

    priors = bot.policy_prior("REACTION", actions)
    assert pytest.approx(sum(priors), rel=1e-9) == 1.0

    pass_prior, pong_prior, hu_prior = priors
    assert hu_prior > pong_prior > pass_prior


def test_tree_reuse_accumulates_visits_between_calls():
    env = Mahjong16Env(_build_rules(), seed=23)
    config = MCTSBotConfig(simulations=6, rollout_depth=2, seed=5, reuse_tree=True)
    bot = MCTSBot(env, config)

    obs = env.reset()
    bot.choose(obs)

    root = bot._root_cache
    assert root is not None
    action_key = bot._last_action_key
    assert action_key is not None
    reused_child = root.children.get(action_key)
    assert reused_child is not None
    previous_visits = reused_child.visits

    bot.choose(obs)

    assert bot._root_cache is reused_child
    assert reused_child.visits > previous_visits
