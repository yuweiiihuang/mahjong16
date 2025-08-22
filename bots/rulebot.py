
from collections import Counter

class RuleBot:
    """極簡啟發式：優先丟出在手牌中出現次數最少的牌；若有 drawn，可能優先丟 drawn。"""
    def select(self, obs):
        legal = obs.get("legal_actions", [])
        discards = [a for a in legal if a["type"] == "DISCARD"]
        if not discards:
            return {"type":"PASS"}
        hand = obs.get("hand", [])
        cnt = Counter(hand)
        # 讓 'from=drawn' 稍微優先（同樣次數時）
        discards.sort(key=lambda a: (cnt.get(a["tile"], 0), 0 if a.get("from")=="drawn" else 1, a["tile"]))
        return discards[0]
