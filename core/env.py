# file: core/env.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import random

from .tiles import full_wall, is_flower, tile_to_str, hand_to_str
from .ruleset import Ruleset
from .hand import is_win_16, waits_after_discard_17
from .judge import settle_scores_stub

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
        # 胡的那張牌（自摸=drawn；榮和=最後那張被胡的棄牌）
        self.win_tile: Optional[int] = None
        # 胡牌當下的回合持有者（自摸時等於 winner；榮和時等於丟牌者）
        self.turn_at_win: Optional[int] = None

        return self._obs(self.turn)

    def legal_actions(self, pid: Optional[int]=None) -> List[Dict[str, Any]]:
        if getattr(self, "done", False):
            return []
        if self.phase == "TURN":
            pid = self.turn if pid is None else pid
            me = self.players[pid]
            acts: List[Dict[str, Any]] = []
            declared_ting = bool(me.get("declared_ting", False))
            if me["drawn"] is not None:
                # 自摸（TSUMO）
                if self.rules.allow_hu and is_win_16(me["hand"] + [me["drawn"]], me["melds"], self.rules):
                    acts.append({"type":"HU", "source":"TSUMO"})
                # 已宣告聽牌 → 只能丟 drawn
                acts.append({"type":"DISCARD", "tile": me["drawn"], "from":"drawn"})
            if not declared_ting:
                # 未聽牌：可丟手牌
                for t in self._legal_discards(pid):
                    acts.append({"type":"DISCARD", "tile": t, "from":"hand"})
                # 產生 TING 選項（宣告聽 + 同步丟該張）
                if self.rules.allow_ting:
                    drawn = me.get("drawn")
                    melds = me.get("melds") or []
                    # 從手牌丟
                    for t in list(self._legal_discards(pid)):
                        waits = waits_after_discard_17(me["hand"], drawn, melds, t, "hand", self.rules)
                        if waits:
                            acts.append({"type":"TING", "tile": t, "from":"hand", "waits": waits})
                    # 從 drawn 丟
                    if drawn is not None:
                        waits = waits_after_discard_17(me["hand"], drawn, melds, drawn, "drawn", self.rules)
                        if waits:
                            acts.append({"type":"TING", "tile": drawn, "from":"drawn", "waits": waits})
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
            ting_locked = bool(self.players[pid].get("declared_ting", False))
            # Chi（僅限下家）
            if (not ting_locked) and ((pid - discard["pid"]) % self.rules.n_players) == 1 and self.rules.allow_chi:
                for a,b in chi_options(tile, self.players[pid]["hand"]):
                    acts.append({"type":"CHI", "use":[a,b]})
            # Pon
            if (not ting_locked) and self.rules.allow_pong and self.players[pid]["hand"].count(tile) >= 2:
                acts.append({"type":"PONG"})
            # Gang（大明槓：手上已有三張，吃入一張成槓）
            if (not ting_locked) and self.rules.allow_gang and self.players[pid]["hand"].count(tile) >= 3:
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
                # 明確標記來源為自摸，並記錄胡牌當下回合屬於誰（即 winner）
                self.win_source = "TSUMO"
                # 自摸的胡牌就是當前 drawn
                self.win_tile = self.players[pid]["drawn"]
                self.turn_at_win = pid
                self.phase = "DONE"
                self.reaction_queue = []
                self.reaction_idx = 0
                self.last_discard = None
                self.done = True
                rewards = settle_scores_stub(self)
                return self._obs(self.turn), rewards, True, {}
            if a_type not in ("DISCARD", "TING"):
                raise AssertionError("本階段僅能丟牌（DISCARD）/自摸（HU）/宣告聽（TING）")
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

            # 若為宣告聽，鎖定之後只能丟 drawn
            if a_type == "TING":
                self.players[pid]["declared_ting"] = True

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
            # 聽牌狀態下的玩家僅能 PASS 或 HU
            if self.players[pid].get("declared_ting", False) and a_type not in ("PASS", "HU"):
                a_type = "PASS"
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
                    # 取出最後一張棄牌與丟牌者
                    discarder = self.last_discard["pid"]
                    tile = self.last_discard["tile"]
                    # 從丟牌者 river 與全局 discard_pile 移除該牌（不再留在河道）
                    rv = self.players[discarder]["river"]
                    if rv and rv[-1] == tile:
                        rv.pop()
                    else:
                        try:
                            rv.remove(tile)
                        except ValueError:
                            pass
                    if self.discard_pile and self.discard_pile[-1] == tile:
                        self.discard_pile.pop()
                    else:
                        try:
                            self.discard_pile.remove(tile)
                        except ValueError:
                            pass
                    # 回傳給上層列印的中標資訊
                    resolved_info = {"pid": claimer, "type": ctype, "tile": tile, "from_pid": discarder}
                    # 棄牌已被取走，不再留在場上
                    self.last_discard = None
                    # 準備回傳給上層列印用的 info
                    info = {"resolved_claim": {
                        "pid": claimer,
                        "type": ctype,
                        "tile": tile,
                        **({"use": resolved.get("use")} if "use" in resolved else {})
                    }}
                    if ctype == "CHI":
                        a,b = resolved["use"]
                        # 從手牌移除兩張，加入明順
                        self.players[claimer]["hand"].remove(a)
                        self.players[claimer]["hand"].remove(b)
                        self.players[claimer]["melds"].append(
                            {"type":"CHI","tiles":[a,b,tile], "from_pid": discarder}
                        )
                        self.players[claimer]["drawn"] = None  # 由吃入，非摸牌
                        self.turn = claimer
                        self.phase = "TURN"  # 直接要求丟牌
                        resolved_info["use"] = [a,b]
                        return self._obs(self.turn), [0]*self.rules.n_players, False, {"resolved_claim": resolved_info}
                    elif ctype == "PONG":
                        # 從手牌移除兩張，加入明刻
                        for _ in range(2):
                            self.players[claimer]["hand"].remove(tile)
                        self.players[claimer]["melds"].append(
                            {"type":"PONG","tiles":[tile,tile,tile], "from_pid": discarder}
                        )
                        self.players[claimer]["drawn"] = None
                        self.turn = claimer
                        self.phase = "TURN"
                        return self._obs(self.turn), [0]*self.rules.n_players, False, {"resolved_claim": resolved_info}
                    elif ctype == "GANG":
                        # 大明槓：移除三張，加入明槓，槓後補摸（不得侵犯尾牌留置）
                        for _ in range(3):
                            self.players[claimer]["hand"].remove(tile)
                        self.players[claimer]["melds"].append(
                            {"type":"GANG","tiles":[tile,tile,tile,tile], "from_pid": discarder}
                        )
                        self.n_gang += 1  # 記錄場上槓數以調整尾牌留置（「一槓一」）
                        self.players[claimer]["drawn"] = None
                        self.turn = claimer
                        self.phase = "TURN"
                        self._draw_to_drawn(self.turn)
                        if self.players[self.turn]["drawn"] is None:
                            # 補摸失敗（已達尾牌留置）→ 流局
                            self.done = True
                            rewards = settle_scores_stub(self)
                            return self._obs(self.turn), rewards, True, {"resolved_claim": resolved_info}
                        return self._obs(self.turn), [0]*self.rules.n_players, False, {"resolved_claim": resolved_info}
                    else:  # HU
                        # 記錄榮和的胡牌（即被吃入的那張棄牌）
                        self.win_tile = tile
                        # 記錄丟牌者（胡牌當下的回合持有者）
                        discarder_pid = discarder

                        self.win_source = "RON"
                        self.winner = claimer
                        self.turn_at_win = discarder_pid
                        self.phase = "DONE"
                        self.reaction_queue = []
                        self.reaction_idx = 0
                        self.done = True
                        rewards = settle_scores_stub(self)
                        return self._obs(self.turn), rewards, True, {"resolved_claim": resolved_info}

    # ====== 內部輔助 ======
    def _new_player(self, pid: int) -> Dict[str, Any]:
        return {
            "id": pid,
            "hand": [],
            "drawn": None,
            "flowers": [],
            "melds": [],
            "river": [],
            "score": 0,
            "declared_ting": False,
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
        # 新規則：若有人 HU，僅在 HU 候選中決定；一家放槍僅能一家胡。
        hu_claims = [c for c in self.claims if c["type"] == "HU"]
        if hu_claims:
            hu_claims.sort(key=lambda c: (c["distance"], c["pid"]))  # 距離近者優先
            return hu_claims[0]
        # 否則按原則：優先度 > 距離 > 玩家編號
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
            "declared_ting": bool(me.get("declared_ting", False)),
            # 公開資訊：所有玩家的副露與棄牌河
            "melds_all": [[m if isinstance(m, dict) else list(m) for m in p["melds"]] for p in self.players],
            "rivers": [list(p["river"]) for p in self.players],
            "n_remaining": len(self.wall),
            "last_discard": dict(self.last_discard) if self.last_discard else None,
            "legal_actions": ([] if is_done else
                          self.legal_actions(pid=None if self.phase == "TURN" else pid)),
        }
        return obs
