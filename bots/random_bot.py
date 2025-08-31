"""Simple random bot that selects a random discard when available."""

import random


class RandomBot:
    """Random policy used for smoke testing and baselines."""

    def __init__(self, seed=None):
        """Initialize bot with optional RNG seed for deterministic choices."""
        self.rng = random.Random(seed)

    def select(self, obs):
        """Pick a random DISCARD from legal actions, otherwise PASS."""
        legal = obs.get("legal_actions", [])
        discards = [a for a in legal if a["type"] == "DISCARD"]
        if discards:
            return self.rng.choice(discards)
        return {"type":"PASS"}
