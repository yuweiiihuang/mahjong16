from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple, Protocol
from bots import GreedyBotStrategy
from ui.console import prompt_turn_action, prompt_reaction_action
from domain.gameplay import Action, Observation

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
        if not acts:
            # TURN phase should always provide at least one legal action, but fall back defensively.
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

        # If we reach here, the action list only contains options the heuristic does not recognise.
        # Choose the first one to avoid emitting an illegal PASS back to the environment.
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
