# bots/greedy.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Iterable

from core.tiles import tile_to_str


class GreedyBotStrategy:
    """Greedy smoke-test bot that aims for shape (not points).

    Decision rule:
    - REACTION: HU if available; else simulate CHI/PONG/GANG vs PASS and pick
      the state with lower heuristic cost.
    - TURN: evaluate all legal discards; prefer the one that minimizes cost
      (tiebreak: prefer discarding honors).

    Heuristic cost (lower is better):
      fixed_melds = number of open melds (CHI/PONG/GANG)
      need = max(0, 5 - fixed_melds)   # Taiwan 16 uses 5 melds
      (m, has_pair) = greedy estimate of how many melds can be formed from hand
      cost = 10 * max(0, need - m)     # penalize missing melds (heavier)
           + 3 * (0 if has_pair else 1)
           + min(3, singles_penalty)   # count of singles capped at 3

    Intended for quick smoke/pressure tests rather than strong play.
    """

    # ===================== 小工具 =====================

    @staticmethod
    def _counts34(tiles: Iterable[int]) -> List[int]:
        """將牌轉為 34 種計數（萬筒條各 9、字 7）。"""
        c = [0] * 34
        for t in tiles:
            if 0 <= t < 34:
                c[t] += 1
        return c

    @staticmethod
    def _greedy_melds_and_pair(counts: List[int]) -> Tuple[int, bool]:
        """
        以貪婪法估計：能做出幾組面子（刻/順），以及是否尚有一對眼。
        不修改輸入的 counts（會先複製）。
        """
        c = counts[:]  # copy
        melds = 0

        # 1) 先吃刻子（對任何格都適用）
        for i in range(34):
            if c[i] >= 3:
                k = c[i] // 3
                melds += k
                c[i] -= 3 * k

        # 2) 再吃順子：0..8、9..17、18..26 三門花色各自處理
        def eat_suit(start: int) -> int:
            m = 0
            end = start + 9   # 該花色的範圍
            while True:
                made = 0
                for i in range(start, end - 2):
                    x = min(c[i], c[i + 1], c[i + 2])
                    if x > 0:
                        c[i] -= x
                        c[i + 1] -= x
                        c[i + 2] -= x
                        m += x
                        made += x
                if made == 0:
                    break
            return m

        melds += eat_suit(0)
        melds += eat_suit(9)
        melds += eat_suit(18)

        # 3) 是否還能留下任一對作眼
        has_pair = any(x >= 2 for x in c)
        return melds, has_pair

    @staticmethod
    def _fixed_melds_count(melds: List[Dict[str, Any]]) -> int:
        """統計現有副露（CHI/PONG/GANG）數量。"""
        return sum(1 for m in (melds or []) if (m.get("type") or "").upper() in ("CHI", "PONG", "GANG"))

    def _heuristic_cost(self, hand: List[int], melds: List[Dict[str, Any]]) -> int:
        """回傳啟發式成本（越小越好）。"""
        fixed_melds = self._fixed_melds_count(melds)
        need = max(0, 5 - fixed_melds)  # 十六張麻將需要 5 組面子
        counts = self._counts34(hand)
        m, has_pair = self._greedy_melds_and_pair(counts)
        missing_melds = max(0, need - m)
        missing_eye = 0 if has_pair else 1
        singles_pen = sum(1 for x in counts if x == 1)
        return missing_melds * 10 + missing_eye * 3 + min(3, singles_pen)

    # ===================== 模擬各種行為後的狀態 =====================

    def _after_discard(self, obs: Dict[str, Any], action: Dict[str, Any]) -> Tuple[List[int], List[Dict[str, Any]]]:
        """
        模擬丟出某張牌後，新的 (手牌, 副露) ；丟 drawn 則手牌不動，丟手牌則把 drawn 併回手。
        僅供評估啟發式，不會影響環境。
        """
        hand = list(obs.get("hand") or [])
        drawn = obs.get("drawn")
        melds = [dict(m) for m in (obs.get("melds") or [])]

        t = action.get("tile")
        src = action.get("from", "hand")
        if src == "drawn":
            # 丟摸來的：手牌維持 16 張，不需變動
            pass
        else:
            # 從手牌丟一張；若當前有 drawn，則 drawn 會併回手牌（維持 16）
            if t in hand:
                hand.remove(t)
            if drawn is not None:
                hand.append(drawn)

        return hand, melds

    def _after_claim(self, obs: Dict[str, Any], action: Dict[str, Any]) -> Tuple[List[int], List[Dict[str, Any]]]:
        """
        模擬 CHI/PONG/GANG 後的 (手牌, 副露)。
        僅用於評估啟發式，不考慮之後立刻要丟哪張。
        """
        hand = list(obs.get("hand") or [])
        melds = [dict(m) for m in (obs.get("melds") or [])]
        last = obs.get("last_discard") or {}
        tile = last.get("tile")
        typ = (action.get("type") or "").upper()

        if typ == "CHI":
            a, b = action.get("use", [None, None])
            if a in hand:
                hand.remove(a)
            if b in hand:
                hand.remove(b)
            melds.append({"type": "CHI", "tiles": [a, b, tile]})
        elif typ == "PONG":
            removed = 0
            for i in range(len(hand) - 1, -1, -1):
                if hand[i] == tile:
                    hand.pop(i)
                    removed += 1
                    if removed == 2:
                        break
            melds.append({"type": "PONG", "tiles": [tile, tile, tile]})
        elif typ == "GANG":
            removed = 0
            for i in range(len(hand) - 1, -1, -1):
                if hand[i] == tile:
                    hand.pop(i)
                    removed += 1
                    if removed == 3:
                        break
            melds.append({"type": "GANG", "tiles": [tile, tile, tile, tile]})

        return hand, melds

    # ===================== 主決策 =====================

    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        """Choose an action in TURN/REACTION to minimize heuristic cost; HU if possible."""
        acts = obs.get("legal_actions", []) or []
        if not acts:
            return {"type": "PASS"}

        # 能胡就胡（包含 TURN 的自摸與 REACTION 的榮和）
        for a in acts:
            if (a.get("type") or "").upper() == "HU":
                return a

        phase = obs.get("phase")

        if phase == "REACTION":
            # 比較 PASS vs CHI/PONG/GANG
            best = {"type": "PASS"}
            best_cost = self._heuristic_cost(
                list(obs.get("hand") or []),
                list(obs.get("melds") or []),
            )
            for a in acts:
                t = (a.get("type") or "").upper()
                if t not in ("CHI", "PONG", "GANG"):
                    continue
                h2, m2 = self._after_claim(obs, a)
                cst = self._heuristic_cost(h2, m2)
                if cst < best_cost:
                    best_cost = cst
                    best = a
            return best

        # phase == "TURN"
        # 若能宣告聽，直接宣告（偏好等待較多者）
        tings = [a for a in acts if (a.get("type") or "").upper() == "TING"]
        if tings:
            tings.sort(key=lambda a: -len(a.get("waits") or []))
            return tings[0]

        # 否則：選擇要丟哪張
        best = None
        best_key = None  # (cost, tie_break)
        for a in acts:
            if (a.get("type") or "").upper() != "DISCARD":
                continue
            h2, m2 = self._after_discard(obs, a)
            cst = self._heuristic_cost(h2, m2)

            # 輕微偏好丟字牌（當成本相同時），讓牌型更容易作順子
            tie_break = 0
            t = a.get("tile")
            lbl = tile_to_str(t)
            if lbl and len(lbl) == 1:  # 字牌 E/S/W/N/C/F/P
                tie_break = -1

            key = (cst, tie_break)
            if best is None or best_key is None or key < best_key:
                best = a
                best_key = key

        return best if best is not None else acts[0]
