"""Regression tests for the Monte Carlo Tree Search bot."""

from __future__ import annotations

from bots import MCTSBot, MCTSBotConfig
from core import Mahjong16Env, Ruleset


def test_mcts_bot_returns_legal_actions():
    rules = Ruleset(
        include_flowers=False,
        dead_wall_mode="fixed",
        dead_wall_base=16,
        scoring_profile="taiwan_base",
        see_flower_see_wind=False,
        randomize_seating_and_dealer=False,
        enable_wind_flower_scoring=False,
        scoring_overrides_path=None,
    )
    env = Mahjong16Env(rules, seed=7)
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
