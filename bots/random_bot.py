
import random

class RandomBot:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def select(self, obs):
        legal = obs.get("legal_actions", [])
        discards = [a for a in legal if a["type"] == "DISCARD"]
        if discards:
            return self.rng.choice(discards)
        return {"type":"PASS"}
