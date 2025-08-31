"""Rule-based minimal bot that discards the least frequent tile in hand."""

from collections import Counter


class RuleBot:
    """Discard the rarest tile; slightly prefer discarding from drawn on ties."""

    def select(self, obs):
        """Choose a DISCARD action based on frequency; PASS if none available."""
        legal = obs.get("legal_actions", [])
        discards = [a for a in legal if a["type"] == "DISCARD"]
        if not discards:
            return {"type":"PASS"}
        hand = obs.get("hand", [])
        cnt = Counter(hand)
        # Prefer 'from=drawn' slightly when counts tie
        discards.sort(key=lambda a: (cnt.get(a["tile"], 0), 0 if a.get("from")=="drawn" else 1, a["tile"]))
        return discards[0]
