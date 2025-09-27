from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple, Protocol
from bots import GreedyBotStrategy
from ui.console import prompt_turn_action, prompt_reaction_action
from core import Action, Observation

# Reaction priority: HU > GANG > PONG > CHI
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}


class Strategy(Protocol):
    """Protocol for strategies used by the demo gameplay loop."""

    def choose(self, obs: Observation) -> Action:
        """Select an action given an observation.

        Args:
          obs: Observation dict from the environment.

        Returns:
          An action dict.
        """


class AutoStrategy:
    """Simple auto strategy: HU if available; otherwise discard policy.

    REACTION phase: prefer highest priority non‑PASS.
    TURN phase: HU if present, otherwise discard drawn, else first legal discard.
    """

    def choose(self, obs: Observation) -> Action:
        acts: List[Action] = obs.get("legal_actions", []) or []
        phase = obs.get("phase")
        if phase == "REACTION":
            cand = [a for a in acts if (a.get("type") or "").upper() != "PASS"]
            if not cand:
                return {"type": "PASS"}
            cand.sort(key=lambda a: PRIORITY.get((a.get("type") or "").upper(), -1), reverse=True)
            return cand[0]
        hu = next((a for a in acts if (a.get("type") or "").upper() == "HU"), None)
        if hu is not None:
            return hu
        drawn_discard = next(
            (a for a in acts if (a.get("type") or "").upper() == "DISCARD" and a.get("from") == "drawn"),
            None
        )
        if drawn_discard is not None:
            return drawn_discard
        for a in acts:
            if (a.get("type") or "").upper() == "DISCARD":
                return a
        return {"type": "PASS"}


class HumanStrategy:
    """Interactive console strategy that renders waits and prompts for input."""

    def choose(self, obs: Observation) -> Action:
        acts: List[Action] = obs.get("legal_actions", []) or []
        phase = obs.get("phase")
        if not acts:
            return {"type": "PASS"}
        if phase == "TURN":
            return prompt_turn_action(obs)
        else:
            return prompt_reaction_action(obs)


def build_strategies(n_players: int, human_pid: Optional[int], bot: str) -> List[Strategy]:
    strategies: List[Strategy] = []
    for pid in range(n_players):
        if human_pid is not None and pid == human_pid:
            strategies.append(HumanStrategy())
        else:
            if bot == "greedy":
                strategies.append(GreedyBotStrategy())
            elif bot == "human":
                strategies.append(HumanStrategy())
            else:
                strategies.append(AutoStrategy())
    return strategies
