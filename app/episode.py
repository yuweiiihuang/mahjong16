"""Drive one hand through player-visible observations and settle its payments."""
from __future__ import annotations

from app.training_export import player_observation
from domain.gameplay.game_env import MahjongEnvironment
from domain.rules.ruleset import Ruleset
from domain.scoring.engine import compute_payments
from domain.scoring.lookup import load_scoring_assets
from domain.scoring.score_types import ScoringContext


def observation(env: MahjongEnvironment, pid: int) -> dict:
    """Adapt the established private-information filter for the existing Greedy bot."""
    obs = player_observation(env, pid)
    obs["melds_all"] = [player["melds"] for player in obs["players"]]
    return obs


class HandEpisode:
    """Advance legal decisions and settle a hand without changing domain rules."""

    def __init__(self, seed: int, rules: Ruleset | None = None,
                 max_steps: int = 2000) -> None:
        self.rules = rules or Ruleset()
        if self.rules.n_players != 4 or max_steps <= 0:
            raise ValueError("HandEpisode requires four players and a positive step limit")
        self.env = MahjongEnvironment(self.rules, seed=seed)
        self.table = load_scoring_assets(
            self.rules.scoring_profile, self.rules.scoring_overrides_path)
        self.max_steps = max_steps
        self.steps = 0
        self.env.reset()

    def current(self) -> dict | None:
        """Return the next actual actor, excluding unanswered cancelled reactions."""
        if self.env.done:
            return None
        pid = (self.env.turn if self.env.phase == "TURN"
               else self.env.pending_reactions()[0])
        return observation(self.env, pid)

    def act(self, action: dict) -> None:
        """Reject invalid decisions before crossing the permissive TURN interface."""
        obs = self.current()
        if obs is None or action not in obs["legal_actions"]:
            raise ValueError("Action is not a current legal candidate")
        if self.steps >= self.max_steps:
            raise RuntimeError("Hand exceeded the engine step limit")
        self.env.step(action, pid=obs["player"])
        self.steps += 1

    def payments(self) -> list[int]:
        """Use the same net settlement as CLI and recorded hands, including flowers."""
        if not self.env.done:
            raise ValueError("Cannot settle an unfinished hand")
        ctx = ScoringContext.from_env(self.env, self.table)
        payments, _ = compute_payments(ctx, self.rules.base_points, self.rules.tai_points)
        if sum(payments) != 0:
            raise RuntimeError("Non-zero-sum hand settlement")
        return payments
