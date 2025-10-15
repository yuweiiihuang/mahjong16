from __future__ import annotations

from typing import List, Optional, Protocol

from domain.gameplay import Action, Observation
from ui.console import prompt_reaction_action, prompt_turn_action

# Reaction priority: HU > GANG > PONG > CHI
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}


class Strategy(Protocol):
    """Protocol for strategies used by the demo gameplay loop."""

    def choose(self, obs: Observation) -> Action:
        """Select an action given an observation."""


class AutoStrategy:
    """Simple auto strategy: HU if available; otherwise discard policy."""

    def choose(self, obs: Observation) -> Action:
        acts: List[Action] = obs.get("legal_actions", []) or []
        phase = obs.get("phase")
        if phase == "REACTION":
            cand = [a for a in acts if (a.get("type") or "").upper() != "PASS"]
            if not cand:
                return {"type": "PASS"}
            cand.sort(key=lambda a: PRIORITY.get((a.get("type") or "").upper(), -1), reverse=True)
            return cand[0]
        if not acts:
            return {"type": "PASS"}

        def find_action(kind: str, predicate=None) -> Optional[Action]:
            for candidate in acts:
                if (candidate.get("type") or "").upper() != kind:
                    continue
                if predicate is None or predicate(candidate):
                    return candidate
            return None

        hu = find_action("HU")
        if hu is not None:
            return hu

        drawn_discard = find_action("DISCARD", lambda a: a.get("from") == "drawn")
        if drawn_discard is not None:
            return drawn_discard

        hand_discard = find_action("DISCARD")
        if hand_discard is not None:
            return hand_discard

        ting = find_action("TING")
        if ting is not None:
            return ting

        gang_like = find_action("ANGANG") or find_action("KAKAN")
        if gang_like is not None:
            return gang_like

        return acts[0]


class HumanStrategy:
    """Interactive console strategy that renders waits and prompts for input."""

    def choose(self, obs: Observation) -> Action:
        acts: List[Action] = obs.get("legal_actions", []) or []
        phase = obs.get("phase")
        if not acts:
            return {"type": "PASS"}
        if phase == "TURN":
            return prompt_turn_action(obs)
        return prompt_reaction_action(obs)


def build_strategies(n_players: int, human_pid: Optional[int], bot: str) -> List[Strategy]:
    """
    Build a list of strategies for each player.

    Args:
        n_players (int): Number of players.
        human_pid (Optional[int]): Player ID for human player, or None.
        bot (str): Bot type, must be one of "greedy", "human", or "auto".

    Returns:
        List[Strategy]: List of strategies for each player.

    Raises:
        ValueError: If bot is not a valid type.
    """
    from bots.greedy import GreedyBotStrategy

    valid_bots = {"greedy", "human", "auto"}
    if bot not in valid_bots:
        raise ValueError(f"Invalid bot type '{bot}'. Valid options are: {', '.join(valid_bots)}.")

    strategies: List[Strategy] = []
    for pid in range(n_players):
        if human_pid is not None and pid == human_pid:
            strategies.append(HumanStrategy())
        else:
            if bot == "greedy":
                strategies.append(GreedyBotStrategy())
            elif bot == "human":
                strategies.append(HumanStrategy())
            else:  # bot == "auto"
                strategies.append(AutoStrategy())
    return strategies


__all__ = ["Strategy", "AutoStrategy", "HumanStrategy", "build_strategies"]
