from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import random

from .tiles import full_wall, is_flower, tile_to_str, hand_to_str
from .ruleset import Ruleset
from .judge import is_win_16, settle_scores_stub

# 反應優先權：胡 > 槓 > 碰 > 吃
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}

def is_suited(t: int) -> bool:
    # 0..8 萬, 9..17 筒, 18..26 條
    return 0 <= t <= 26

def suit_of(t: int) -> int:
    # 0:萬, 1:筒, 2:條, 3:字
    if 0 <= t <= 8: return 0
    if 9 <= t <= 17: return 1
    if 18 <= t <= 26: return 2
    return 3

def rank_of(t: int) -> Optional[int]:
    if not is_suited(t): return None
    if 0 <= t <= 8: return t - 0 + 1
    if 9 <= t <= 17: return t - 9 + 1
    if 18 <= t <= 26: return t - 18 + 1
    return None

def chi_options(discard_tile: int, hand: List[int]) -> List[Tuple[int,int]]:
    """列舉所有可吃的兩張（僅限下家；不含字牌）。回傳 [(a,b), ...]，代表以 a,b + discard_tile 成順子。"""
    if not is_suited(discard_tile): return []
    r = rank_of(discard_tile)
    s = suit_of(discard_tile)
    candidates = []
    # 三種可能： (r-2,r-1), (r-1,r+1), (r+1,r+2)
    patterns = [(-2,-1), (-1,1), (1,2)]
    for dx, dy in patterns:
        r1, r2 = r+dx, r+dy
        if not (1 <= r1 <= 9 and 1 <= r2 <= 9): continue
        # 轉回 tile id
        base = 0 if s==0 else (9 if s==1 else 18)
        a, b = base + (r1-1), base + (r2-1)
        if hand.count(a) >= 1 and hand.count(b) >= 1:
            candidates.append((a,b))
    return candidates

class Mahjong16Env:
    """
    台麻16簡化環境（含 drawn、反應視窗、尾牌留置）：
    - 每家持有 16 張；輪到該家時，摸 1 張至 `drawn`（第17張），再丟回 1 張。
    - 丟牌後進入反應視窗：依「胡>槓>碰>吃」與距離（近優先）決定插入行動。
    - 尾牌留置：依 rules.dead_wall_mode / dead_wall_base 決定是否允許摸牌；若無法摸牌則流局。
    - 目前支援：DISCARD、反應（CHI/PONG/GANG/HU）與簡化的大明槓（槓後補摸）。
    - TODO：加槓/暗槓、自摸胡/結算（judge.is_win_16 尚未完成，HU 分支通常不會觸發）。
    """
    def __init__(self, rules: Ruleset, seed: Optional[int]=None):
        self.rules = rules
        self.rng = random.Random(seed)
        self.reset_rng_seed = seed

    # ====== 尾牌留置（流局）判斷 ======
    def _dead_wall_reserved(self) -> int:
        """計算目前尾牌留置張數（dead wall）。"""
        mode = getattr(self.rules, "dead_wall_mode", "fixed")
        base = getattr(self.rules, "dead_wall_base", 16)
        if mode == "gang_plus_one":
            return base + getattr(self, "n_gang", 0)
        return base

    def _can_draw_from_wall(self) -> bool:
        """檢查是否還能從牆摸牌（不得侵犯尾牌留置）。"""
        return len(self.wall) > self._dead_wall_reserved()

    # ====== API ======
    def reset(self) -> Dict[str, Any]:
        self.wall: List[int] = full_wall(self.rules.include_flowers, self.rng)
        self.discard_pile: List[int] = []
        self.players: List[Dict[str, Any]] = [self._new_player(i) for i in range(self.rules.n_players)]
        self.n_gang: int = 0  # 場上槓數（供「一槓一」模式計算尾牌留置）
        self.turn = 0  # 莊家
        self.phase = "TURN"  # or "REACTION"
        self.reaction_queue: List[int] = []   # 要依序詢問反應的玩家（丟牌者之下一家開始）
        self.reaction_idx: int = 0
        self.claims: List[Dict[str, Any]] = []

        # 發牌：每家 16 張（補花到非花）；直接放入手牌
        for _ in range(self.rules.initial_hand):
            for pid in range(self.rules.n_players):
                self._draw_into_hand(pid)

        # 莊家先摸一張至 drawn（16+drawn=17）
        self._draw_to_drawn(0)

        self.last_discard: Optional[Dict[str, Any]] = None
        self.done = False
        self.winner: Optional[int] = None
        self.win_source: Optional[str] = None

        return self._obs(self.turn)

    def legal_actions(self, pid: Optional[int]=None) -> List[Dict[str, Any]]:
        if getattr(self, "done", False):
            return []
        if self.phase == "TURN":
            pid = self.turn if pid is None else pid
            me = self.players[pid]
            acts: List[Dict[str, Any]] = []
            if me["drawn"] is not None:
                # 自摸（TSUMO）
                if self.rules.allow_hu and is_win_16(me["hand"] + [me["drawn"]], me["melds"], self.rules):
                    acts.append({"type":"HU", "source":"TSUMO"})
                acts.append({"type":"DISCARD", "tile": me["drawn"], "from":"drawn"})
            for t in self._legal_discards(pid):
                acts.append({"type":"DISCARD", "tile": t, "from":"hand"})
            # TODO：加槓/暗槓等
            return acts
        else:  # REACTION
            if not self.reaction_queue or not (0 <= self.reaction_idx < len(self.reaction_queue)):
                return []
            # 當前要回應的玩家
            pid = self.reaction_queue[self.reaction_idx]
            acts: List[Dict[str, Any]] = [{"type":"PASS"}]
            discard = self.last_discard
            if discard is None:
                return acts
            tile = discard["tile"]
            # Chi（僅限下家）
            if ((pid - discard["pid"]) % self.rules.n_players) == 1 and self.rules.allow_chi:
                for a,b in chi_options(tile, self.players[pid]["hand"]):
                    acts.append({"type":"CHI", "use":[a,b]})
            # Pon
            if self.rules.allow_pong and self.players[pid]["hand"].count(tile) >= 2:
                acts.append({"type":"PONG"})
            # Gang（大明槓：手上已有三張，吃入一張成槓）
            if self.rules.allow_gang and self.players[pid]["hand"].count(tile) >= 3:
                acts.append({"type":"GANG"})
            # Hu（依胡牌判定；目前 judge.is_win_16 尚未實作，通常不會出現）
            if self.rules.allow_hu and is_win_16(self.players[pid]["hand"] + [tile], self.players[pid]["melds"], self.rules):
                acts.append({"type":"HU"})
            return acts

    def step(self, action: Dict[str, Any]):
        assert not self.done, "episode is done"

        if self.phase == "TURN":
            pid = self.turn
            a_type = action.get("type")
            # 支援自摸結束
            if a_type == "HU":
                self.winner = pid
                self.phase = "DONE"
                self.reaction_queue = []
                self.reaction_idx = 0
                self.last_discard = None
                self.done = True
                rewards = settle_scores_stub(self)
                return self._obs(self.turn), rewards, True, {}
            if a_type != "DISCARD":
                raise AssertionError("本階段僅能丟牌（DISCARD）或自摸（ZIMO）")
            src = action.get("from", "hand")
            tile = action["tile"]

            if src == "drawn":
                assert self.players[pid]["drawn"] == tile, "丟牌來源為 drawn，但牌不相符"
                self.players[pid]["drawn"] = None
            else:
                assert tile in self.players[pid]["hand"] and (not is_flower(tile)), "非法丟手牌"
                self.players[pid]["hand"].remove(tile)
                if self.players[pid]["drawn"] is not None:
                    self.players[pid]["hand"].append(self.players[pid]["drawn"])  # 併回手牌維持16
                    self.players[pid]["drawn"] = None

            # 進捨牌河與記錄
            self.players[pid]["river"].append(tile)
            self.discard_pile.append(tile)
            self.last_discard = {"pid": pid, "tile": tile}

            # 開啟反應視窗
            self.phase = "REACTION"
            self.reaction_queue = [ (pid + i) % self.rules.n_players for i in (1,2,3) ]  # 下家起
            self.reaction_idx = 0
            self.claims = []

            # 下一個要動作的是第一位反應者
            next_pid = self.reaction_queue[self.reaction_idx]
            return self._obs(next_pid), [0]*self.rules.n_players, False, {}

        else:  # REACTION
            pid = self.reaction_queue[self.reaction_idx]
            a_type = action.get("type")
            assert a_type in ("PASS","CHI","PONG","GANG","HU"), "反應期僅允許 PASS/CHI/PONG/GANG/HU"
            if a_type != "PASS":
                # 記錄宣告（用於最後決議）
                claim = {"pid": pid, "type": a_type}
                # 距離：越小越近
                dist = (pid - self.last_discard["pid"]) % self.rules.n_players
                if dist == 0: dist = self.rules.n_players  # 不應發生
                claim["distance"] = dist
                claim["priority"] = PRIORITY[a_type]
                if a_type == "CHI":
                    use = action.get("use")
                    assert isinstance(use, list) and len(use)==2, "CHI 需指定兩張手牌"
                    claim["use"] = use
                self.claims.append(claim)
            # 前進到下一位反應者或結束反應視窗
            self.reaction_idx += 1
            if self.reaction_idx < len(self.reaction_queue):
                next_pid = self.reaction_queue[self.reaction_idx]
                return self._obs(next_pid), [0]*self.rules.n_players, False, {}
            else:
                # 結束反應視窗，進入決議
                resolved = self._resolve_claims()
                if resolved is None:
                    # 無人宣告：進入下一家摸牌（不得侵犯尾牌留置；若無法摸則流局）
                    self.phase = "TURN"
                    self.turn = (self.last_discard["pid"] + 1) % self.rules.n_players
                    self._draw_to_drawn(self.turn)
                    if self.players[self.turn]["drawn"] is None:
                        # 無法摸牌（已達尾牌留置）→ 立刻流局
                        self.done = True
                        rewards = settle_scores_stub(self)
                        return self._obs(self.turn), rewards, True, {}
                    return self._obs(self.turn), [0]*self.rules.n_players, False, {}
                else:
                    # 有宣告者：套用
                    claimer = resolved["pid"]
                    ctype = resolved["type"]
                    tile = self.last_discard["tile"]
                    self.last_discard = None  # 被吃碰槓後，棄牌不在場上
                    if ctype == "CHI":
                        a,b = resolved["use"]
                        # 從手牌移除兩張，加入明順
                        self.players[claimer]["hand"].remove(a)
                        self.players[claimer]["hand"].remove(b)
                        self.players[claimer]["melds"].append({"type":"CHI","tiles":[a,b,tile]})
                        self.players[claimer]["drawn"] = None  # 由吃入，非摸牌
                        self.turn = claimer
                        self.phase = "TURN"  # 直接要求丟牌
                        return self._obs(self.turn), [0]*self.rules.n_players, False, {}
                    elif ctype == "PONG":
                        # 從手牌移除兩張，加入明刻
                        for _ in range(2):
                            self.players[claimer]["hand"].remove(tile)
                        self.players[claimer]["melds"].append({"type":"PONG","tiles":[tile,tile,tile]})
                        self.players[claimer]["drawn"] = None
                        self.turn = claimer
                        self.phase = "TURN"
                        return self._obs(self.turn), [0]*self.rules.n_players, False, {}
                    elif ctype == "GANG":
                        # 大明槓：移除三張，加入明槓，槓後補摸（不得侵犯尾牌留置）
                        for _ in range(3):
                            self.players[claimer]["hand"].remove(tile)
                        self.players[claimer]["melds"].append({"type":"GANG","tiles":[tile,tile,tile,tile]})
                        self.n_gang += 1  # 記錄場上槓數以調整尾牌留置（「一槓一」）
                        self.players[claimer]["drawn"] = None
                        self.turn = claimer
                        self.phase = "TURN"
                        self._draw_to_drawn(self.turn)
                        if self.players[self.turn]["drawn"] is None:
                            # 補摸失敗（已達尾牌留置）→ 流局
                            self.done = True
                            rewards = settle_scores_stub(self)
                            return self._obs(self.turn), rewards, True, {}
                        return self._obs(self.turn), [0]*self.rules.n_players, False, {}
                    else:  # HU
                        # 判胡：目前 judge.is_win_16 未實作，此分支暫不會觸發
                        self.win_source = "RON"
                        self.winner = claimer
                        self.phase = "DONE"
                        self.reaction_queue = []
                        self.reaction_idx = 0
                        self.done = True
                        rewards = settle_scores_stub(self)
                        return self._obs(self.turn), rewards, True, {}

    # ====== 內部輔助 ======
    def _new_player(self, pid: int) -> Dict[str, Any]:
        return {
            "id": pid,
            "hand": [],
            "drawn": None,
            "flowers": [],
            "melds": [],
            "river": [],
            "score": 0
        }

    def _draw_into_hand(self, pid: int):
        while self._can_draw_from_wall():
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                self.players[pid]["flowers"].append(t)
                continue
            self.players[pid]["hand"].append(t)
            break

    def _draw_to_drawn(self, pid: int):
        self.players[pid]["drawn"] = None
        while self._can_draw_from_wall():
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                self.players[pid]["flowers"].append(t)
                continue
            self.players[pid]["drawn"] = t
            break

    def _legal_discards(self, pid: int):
        from .tiles import is_flower  # 重新導入以防循環
        return [t for t in self.players[pid]["hand"] if not is_flower(t)]

    def _resolve_claims(self) -> Optional[Dict[str, Any]]:
        """根據優先權與距離，選擇最終中標者。回傳 claim 或 None。"""
        if not self.claims:
            return None
        # 最高 priority；若同 priority，距離（1 最近）優先；仍同則以玩家編號小者（穩定）
        self.claims.sort(key=lambda c: (-c["priority"], c["distance"], c["pid"]))
        return self.claims[0]

    def _obs(self, pid: int) -> Dict[str, Any]:
        me = self.players[pid]
        is_done = getattr(self, "done", False)
        obs = {
            "player": pid,
            "phase": self.phase,
            "hand": list(me["hand"]),
            "drawn": me["drawn"],
            "flowers": list(me["flowers"]),
            "melds": [m if isinstance(m, dict) else list(m) for m in me["melds"]],
            "rivers": [list(p["river"]) for p in self.players],
            "n_remaining": len(self.wall),
            "last_discard": dict(self.last_discard) if self.last_discard else None,
            "legal_actions": ([] if is_done else
                          self.legal_actions(pid=None if self.phase == "TURN" else pid)),
        }
        return obs
