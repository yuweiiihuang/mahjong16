"""Convenience exports for Mahjong16 bots.

The :mod:`bots` package bundles simple heuristic players as well as the
search-based :class:`~bots.mcts.MCTSBot`. Instantiate :class:`MCTSBot`
with a running :class:`core.env.Mahjong16Env` instance and an optional
configuration to adjust simulation count or rollout depth.
"""

from .greedy import GreedyBotStrategy
from .mcts import MCTSBot, MCTSBotConfig
from .random_bot import RandomBot
from .rulebot import RuleBot

__all__ = [
    "GreedyBotStrategy",
    "MCTSBot",
    "MCTSBotConfig",
    "RandomBot",
    "RuleBot",
]