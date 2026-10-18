"""Causal, same-player decision memory shared by data collection and inference."""
from __future__ import annotations

from collections import deque

from rl.encoding import encode

HISTORY_LENGTH = 3


class DecisionHistory:
    """Keep three prior visible states and chosen actions within a single hand."""

    def __init__(self) -> None:
        self.player: int | None = None
        self.entries: deque = deque(maxlen=HISTORY_LENGTH)

    def observe(self, obs: dict) -> dict:
        """Snapshot prior decisions, excluding this decision's action and future labels."""
        if self.player is not None and self.player != obs["player"]:
            raise ValueError("Decision history belongs to a different player")
        return {**obs, "decision_history": list(self.entries)}

    def append(self, obs: dict, action: dict) -> None:
        """Record an already selected legal action after its observation was consumed."""
        if self.player is not None and self.player != obs["player"]:
            raise ValueError("Decision history belongs to a different player")
        state, actions = encode(obs)
        selected = obs["legal_actions"].index(action)
        self.player = obs["player"]
        self.entries.append((state, actions[selected]))
