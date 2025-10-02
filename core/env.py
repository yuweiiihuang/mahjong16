# file: core/env.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import random

from .tiles import full_wall, is_flower, tile_to_str, hand_to_str, N_TILES, N_FLOWERS
from .ruleset import Ruleset
from .hand import is_win_16, waits_after_discard_17
from .types import Action, Observation

# 反應優先權：胡 > 槓 > 碰 > 吃
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}

def is_suited(t: int) -> bool:
    """Return True if tile id is a suited (萬/筒/條) tile.

    Indexing convention:
    - 0..8: 萬, 9..17: 筒, 18..26: 條, 27..33: 字
    """
    return 0 <= t <= 26

def suit_of(t: int) -> int:
    """Return suit index of a tile id: 0=萬, 1=筒, 2=條, 3=字。"""
    if 0 <= t <= 8: return 0
    if 9 <= t <= 17: return 1
    if 18 <= t <= 26: return 2
    return 3

def rank_of(t: int) -> Optional[int]:
    """Return rank (1..9) for suited tiles; None for honors/flowers."""
    if not is_suited(t): return None
    if 0 <= t <= 8: return t - 0 + 1
    if 9 <= t <= 17: return t - 9 + 1
    if 18 <= t <= 26: return t - 18 + 1
    return None

def chi_options(discard_tile: int, hand: List[int]) -> List[Tuple[int,int]]:
    """Enumerate all 2‑tile choices (a,b) from hand that can CHI the discard.

    Only suited tiles and immediate neighbor patterns are considered:
      (r-2,r-1), (r-1,r+1), (r+1,r+2)
    """
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
    """Taiwan 16‑tile Mahjong single‑table environment.

    Mechanics:
    - Each player holds 16 tiles; on their turn they draw into `drawn` (17th), then discard one.
    - After a discard, a reaction window opens: HU > GANG > PONG > CHI by priority and distance.
    - Dead‑wall reservation: drawing stops when only reserved tiles remain (flow).
    - Supports DISCARD, reactions (CHI/PONG/GANG/HU), and exposed ka‑kan (daminggang) with draw.
    """
    def __init__(self, rules: Ruleset, seed: Optional[int]=None):
        """Initialize environment with rules and optional RNG seed."""
        self.rules = rules
        self.rng = random.Random(seed)
        self.reset_rng_seed = seed

    # ====== 尾牌留置（流局）判斷 ======
    def _dead_wall_reserved(self) -> int:
        """Compute reserved tail length based on rules and number of gangs so far."""
        mode = getattr(self.rules, "dead_wall_mode", "fixed")
        base = getattr(self.rules, "dead_wall_base", 16)
        if mode == "gang_plus_one":
            return base + getattr(self, "n_gang", 0)
        return base

    def _can_draw_from_wall(self) -> bool:
        """Return True if we can still draw from the wall (not violating reserved tail)."""
        return len(self.wall) > self._dead_wall_reserved()

    # ====== API ======
    def reset(self) -> Observation:
        """Reset the table, deal hands, and return the first observation for the dealer."""
        self.wall: List[int] = full_wall(self.rules.include_flowers, self.rng)
        self.discard_pile: List[int] = []
        self.discard_count: int = 0
        self.total_open_melds: int = 0
        self.flower_win_type: str | None = None
        self._flower_sets: List[set[int]] = [set() for _ in range(self.rules.n_players)]
        self._flower_union: set[int] = set()
        self.players: List[Dict[str, Any]] = [self._new_player(i) for i in range(self.rules.n_players)]
        self.n_gang: int = 0  # 場上槓數（供「一槓一」模式計算尾牌留置）
        # ====== 風位與莊家 / 座次 ======
        winds_cycle = ["E", "S", "W", "N"]
        # 優先採用外部預設的 pid->風位（供 TableManager 餵入）
        preset_winds = getattr(self, "preset_seat_winds", None)
        if isinstance(preset_winds, list) and len(preset_winds) == self.rules.n_players:
            self.seat_winds = list(preset_winds)
        else:
            if getattr(self.rules, "randomize_seating_and_dealer", False):
                # 完整打亂相對座次：建立 seating_order 並依序指派 ESWN 給各 pid
                order = list(range(self.rules.n_players))
                self.rng.shuffle(order)
                winds = [None] * self.rules.n_players
                for i, pid in enumerate(order):
                    winds[pid] = winds_cycle[i]
                self.seat_winds = winds
            else:
                # 固定：P0=東、P1=南、P2=西、P3=北
                self.seat_winds = winds_cycle[: self.rules.n_players]

        # 由 seat_winds 推導圓桌座次（索引0=東、1=南、2=西、3=北）
        try:
            order_map = {w: i for i, w in enumerate(winds_cycle)}
            pairs = [(order_map.get(w, 99), pid) for pid, w in enumerate(self.seat_winds)]
            pairs.sort()
            self.seating_order = [pid for _, pid in pairs if _ != 99]
        except Exception:
            self.seating_order = list(range(self.rules.n_players))
        # 反查：pid -> 座位索引
        self._seat_index = {pid: i for i, pid in enumerate(self.seating_order)}

        preset_dealer_pid = getattr(self, "preset_dealer_pid", None)
        if isinstance(preset_dealer_pid, int) and 0 <= preset_dealer_pid < self.rules.n_players:
            self.dealer_pid = int(preset_dealer_pid)
        else:
            # 開局莊家為東（座次索引0）
            self.dealer_pid = self.seating_order[0] if self.seating_order else 0

        # 圈風：優先採用外部預設；預設 'E'
        self.quan_feng: str = (getattr(self, "preset_quan_feng", None) or getattr(self, "quan_feng", "E") or "E")
        # 連莊次數：優先採用外部預設（起手 0）
        ds = getattr(self, "preset_dealer_streak", None)
        self.dealer_streak = int(ds) if isinstance(ds, int) else 0
        self.winner_is_dealer: bool = False

        # 起手回合從莊家開始
        self.turn = self.dealer_pid
        self.phase = "TURN"  # or "REACTION"
        self.reaction_queue: List[int] = []   # 要依序詢問反應的玩家（丟牌者之下一家開始）
        self.reaction_idx: int = 0
        self.claims: List[Dict[str, Any]] = []

        # 發牌：每家 16 張（補花到非花）；直接放入手牌
        # 按座次（ESWN）之順序發牌
        order_pids: List[int] = list(self.seating_order) if getattr(self, "seating_order", None) else list(range(self.rules.n_players))
        for _ in range(self.rules.initial_hand):
            for pid in order_pids:
                self._draw_into_hand(pid)
                if getattr(self, "done", False):
                    break
            if getattr(self, "done", False):
                break

        # 莊家先摸一張至 drawn（16+drawn=17）
        if not getattr(self, "done", False):
            self._draw_to_drawn(self.dealer_pid)

        self.last_discard: Optional[Dict[str, Any]] = None
        self.done = False
        self.winner: Optional[int] = None
        self.win_source: Optional[str] = None
        # 胡的那張牌（自摸=drawn；榮和=最後那張被胡的棄牌）
        self.win_tile: Optional[int] = None
        # 胡牌當下的回合持有者（自摸時等於 winner；榮和時等於丟牌者）
        self.turn_at_win: Optional[int] = None

        # 進階：槓相關旗標
        self.win_by_gang_draw: bool = False      # 槓上自摸
        self.win_by_qiang_gang: bool = False     # 搶槓
        self._recent_gang_draw_pid: Optional[int] = None  # 剛補摸者
        self.qiang_gang_mode: bool = False       # 是否進入搶槓反應
        self.pending_kakan: Optional[Dict[str, Any]] = None  # {pid,tile}

        return self._obs(self.turn)

    def legal_actions(self, pid: Optional[int]=None) -> List[Action]:
        """List legal actions for current player (TURN) or current reactor (REACTION)."""
        if getattr(self, "done", False):
            return []
        if self.phase == "TURN":
            pid = self.turn if pid is None else pid
            me = self.players[pid]
            acts: List[Action] = []
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
            # 加入自家回合的槓選項：暗槓 / 加槓
            if self.rules.allow_gang:
                all_tiles = list(me["hand"]) + ([me["drawn"]] if me["drawn"] is not None else [])
                # 暗槓：四張同牌皆在自家（摸牌後）
                for t in set(all_tiles):
                    if not is_flower(t) and all_tiles.count(t) >= 4:
                        acts.append({"type": "ANGANG", "tile": t})
                # 加槓：先前已有 PONG，且手上/摸到第4張
                pong_bases: List[int] = []
                for m in (me.get("melds") or []):
                    if (m.get("type") or "").upper() == "PONG":
                        tiles_m = list(m.get("tiles") or [])
                        if tiles_m:
                            pong_bases.append(tiles_m[0])
                for base in set(pong_bases):
                    if all_tiles.count(base) >= 1:
                        acts.append({"type": "KAKAN", "tile": base})
            return acts
        else:  # REACTION
            if not self.reaction_queue or not (0 <= self.reaction_idx < len(self.reaction_queue)):
                return []
            # 當前要回應的玩家
            pid = self.reaction_queue[self.reaction_idx]
            acts: List[Action] = [{"type":"PASS"}]
            discard = self.last_discard
            if discard is None:
                return acts
            tile = discard["tile"]
            ting_locked = bool(self.players[pid].get("declared_ting", False))
            # 搶槓反應期：僅允許 PASS、HU
            if self.qiang_gang_mode:
                if self.rules.allow_hu and is_win_16(self.players[pid]["hand"] + [tile], self.players[pid]["melds"], self.rules):
                    acts.append({"type":"HU"})
                return acts
            # Chi（僅限下家）
            if (not ting_locked) and (self._seat_index.get(pid) == (self._seat_index.get(discard["pid"], -999) + 1) % self.rules.n_players) and self.rules.allow_chi:
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

    def step(self, action: Action) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        """Apply an action and advance the environment.

        Returns: (obs, rewards, done, info)
        - obs: next observation for the next actor
        - rewards: list per player (zeros here; scoring happens outside env)
        - done: True if the hand ends
        - info: optional metadata including resolved reactions
        """
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
                # 是否為莊家胡
                self.winner_is_dealer = (pid == getattr(self, "dealer_pid", 0))
                # 槓上自摸判定
                if self._recent_gang_draw_pid == pid:
                    self.win_by_gang_draw = True
                self.phase = "DONE"
                self.reaction_queue = []
                self.reaction_idx = 0
                self.last_discard = None
                self.done = True
                rewards = [0] * self.rules.n_players
                return self._obs(self.turn), rewards, True, {}
            # 暗槓：直接成槓並補摸
            if a_type == "ANGANG":
                t = action.get("tile")
                me = self.players[pid]
                all_tiles = list(me["hand"]) + ([me["drawn"]] if me["drawn"] is not None else [])
                assert all_tiles.count(t) >= 4, "暗槓需手牌+摸牌共4張同牌"
                # 移除四張（優先從手牌移除）
                removed = 0
                while removed < 4 and t in me["hand"]:
                    me["hand"].remove(t)
                    removed += 1
                if removed < 4 and me["drawn"] == t:
                    me["drawn"] = None
                    removed += 1
                while removed < 4 and t in me["hand"]:
                    me["hand"].remove(t)
                    removed += 1
                assert removed == 4
                me["melds"].append({"type": "ANGANG", "tiles": [t, t, t, t], "from_pid": None})
                self.n_gang += 1
                # 槓後補摸
                self._draw_to_drawn(pid)
                self._recent_gang_draw_pid = pid
                if self.players[pid]["drawn"] is None:
                    # 無法補摸 → 流局
                    self.done = True
                    rewards = [0] * self.rules.n_players
                    return self._obs(self.turn), rewards, True, {}
                return self._obs(self.turn), [0]*self.rules.n_players, False, {}
            # 加槓：開啟搶槓反應視窗；若無人胡再生效與補摸
            if a_type == "KAKAN":
                t = action.get("tile")
                me = self.players[pid]
                has_pong = any((m.get("type") or "").upper() == "PONG" and (m.get("tiles") or [None])[0] == t for m in (me.get("melds") or []))
                all_tiles = list(me["hand"]) + ([me["drawn"]] if me["drawn"] is not None else [])
                assert has_pong and all_tiles.count(t) >= 1, "加槓需已有 PONG 且持有第4張"
                # 開啟搶槓反應
                self.qiang_gang_mode = True
                self.pending_kakan = {"pid": pid, "tile": t}
                self.last_discard = {"pid": pid, "tile": t}
                self.phase = "REACTION"
                self.reaction_queue = [ self.seating_order[(self._seat_index.get(pid, 0) + i) % self.rules.n_players] for i in (1,2,3) ]
                self.reaction_idx = 0
                self.claims = []
                next_pid = self.reaction_queue[self.reaction_idx]
                return self._obs(next_pid), [0]*self.rules.n_players, False, {}
            if a_type not in ("DISCARD", "TING"):
                raise AssertionError("本階段僅能丟牌/自摸/宣告聽/暗槓/加槓")
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
            self.discard_count += 1
            self.last_discard = {"pid": pid, "tile": tile}

            # 若為宣告聽，鎖定之後只能丟 drawn
            if a_type == "TING":
                self.players[pid]["declared_ting"] = True
                self.players[pid]["ting_declared_at"] = self.discard_count
                self.players[pid]["ting_declared_open_melds"] = self.total_open_melds

            # 開啟反應視窗
            self.phase = "REACTION"
            self.reaction_queue = [ self.seating_order[(self._seat_index.get(pid, 0) + i) % self.rules.n_players] for i in (1,2,3) ]  # 下家起
            self.reaction_idx = 0
            self.claims = []
            # 丟牌之後重置槓上的候選狀態
            self._recent_gang_draw_pid = None

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
                # 距離：越小越近（依座次）
                dist = (self._seat_index.get(pid, 0) - self._seat_index.get(self.last_discard["pid"], 0)) % self.rules.n_players
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
                    # 搶槓窗口無人胡：執行加槓，補摸
                    if self.qiang_gang_mode and self.pending_kakan:
                        kpid = self.pending_kakan.get("pid")
                        ktile = self.pending_kakan.get("tile")
                        me = self.players[kpid]
                        # 使用第4張（優先用 drawn）
                        if me["drawn"] == ktile:
                            me["drawn"] = None
                        else:
                            me["hand"].remove(ktile)
                        # 將對應 PONG 升級為 KAKAN
                        for m in (me.get("melds") or []):
                            if (m.get("type") or "").upper() == "PONG" and (m.get("tiles") or [None])[0] == ktile:
                                m["type"] = "KAKAN"
                                m["tiles"] = [ktile, ktile, ktile, ktile]
                                break
                        self.n_gang += 1
                        # 清理搶槓狀態
                        self.qiang_gang_mode = False
                        self.pending_kakan = None
                        # 補摸到 kpid 的 drawn（仍輪到自己）
                        self.turn = kpid
                        self.phase = "TURN"
                        self._draw_to_drawn(kpid)
                        self._recent_gang_draw_pid = kpid
                        self.last_discard = None
                        if self.players[kpid]["drawn"] is None:
                            self.done = True
                            rewards = [0] * self.rules.n_players
                            return self._obs(self.turn), rewards, True, {}
                        return self._obs(self.turn), [0]*self.rules.n_players, False, {}
                    # 無人宣告：進入下一家摸牌（不得侵犯尾牌留置；若無法摸則流局）
                    self.phase = "TURN"
                    base_idx = self._seat_index.get(self.last_discard["pid"], 0)
                    self.turn = self.seating_order[(base_idx + 1) % self.rules.n_players]
                    self._draw_to_drawn(self.turn)
                    if self.players[self.turn]["drawn"] is None:
                        # 無法摸牌（已達尾牌留置）→ 立刻流局
                        self.done = True
                        rewards = [0] * self.rules.n_players
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
                        self.total_open_melds += 1
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
                        self.total_open_melds += 1
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
                        self.total_open_melds += 1
                        self.n_gang += 1  # 記錄場上槓數以調整尾牌留置（「一槓一」）
                        self.players[claimer]["drawn"] = None
                        self.turn = claimer
                        self.phase = "TURN"
                        self._draw_to_drawn(self.turn)
                        if self.players[self.turn]["drawn"] is None:
                            # 補摸失敗（已達尾牌留置）→ 流局
                            self.done = True
                            rewards = [0] * self.rules.n_players
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
                        # 是否為莊家胡
                        self.winner_is_dealer = (claimer == getattr(self, "dealer_pid", 0))
                        # 搶槓胡的標記
                        if self.qiang_gang_mode:
                            self.win_by_qiang_gang = True
                        # 清理搶槓狀態
                        self.qiang_gang_mode = False
                        self.pending_kakan = None
                        self.phase = "DONE"
                        self.reaction_queue = []
                        self.reaction_idx = 0
                        self.done = True
                        rewards = [0] * self.rules.n_players
                        return self._obs(self.turn), rewards, True, {"resolved_claim": resolved_info}

    # ====== 內部輔助 ======
    def _new_player(self, pid: int) -> Dict[str, Any]:
        """Create initial player dict state."""
        return {
            "id": pid,
            "hand": [],
            "drawn": None,
            "flowers": [],
            "melds": [],
            "river": [],
            "score": 0,
            "declared_ting": False,
            "ting_declared_at": None,
            "ting_declared_open_melds": None,
        }

    def _flower_no(self, tile: int) -> int | None:
        """Map a flower tile id to its ordinal number (F1..F8 -> 1..8)."""
        if not is_flower(tile):
            return None
        return tile - N_TILES + 1

    def _find_flower_holder(self, flower_no: int) -> tuple[int | None, int | None]:
        """Return (pid, tile_id) for the player holding a specific flower number."""
        for pid, player in enumerate(self.players):
            for t in player.get("flowers", []):
                if self._flower_no(t) == flower_no:
                    return pid, t
        return None, None

    def _resolve_flower_win(
        self,
        winner_pid: int,
        loser_pid: int | None,
        win_tile: int | None,
        flower_type: str,
        win_source: str,
    ) -> None:
        """Finalize a round resolved by a flower-specific win condition."""

        self.flower_win_type = flower_type
        self.winner = winner_pid
        self.win_source = win_source
        self.win_tile = win_tile
        self.turn = winner_pid
        self.turn_at_win = winner_pid if win_source == "TSUMO" else loser_pid
        self.winner_is_dealer = (winner_pid == getattr(self, "dealer_pid", 0))
        self.win_by_gang_draw = False
        self.win_by_qiang_gang = False
        self.last_discard = None
        self.done = True
        self.phase = "DONE"
        self.reaction_queue = []
        self.reaction_idx = 0
        self.claims = []
        self.qiang_gang_mode = False
        self.pending_kakan = None

    def _register_flower(self, pid: int, tile: int) -> bool:
        """Add a flower to the player's collection and check special win cases.

        Returns True when a flower-based win ends the round and drawing should stop.
        """

        self.players[pid]["flowers"].append(tile)

        if not getattr(self.rules, "enable_flower_wins", True):
            return False

        flower_no = self._flower_no(tile)
        if flower_no is None:
            return False

        if pid < len(self._flower_sets):
            self._flower_sets[pid].add(flower_no)
        else:
            self._flower_sets.append({flower_no})
        self._flower_union.add(flower_no)

        if getattr(self, "done", False):
            return True

        if len(self._flower_union) < N_FLOWERS:
            return False

        # 八仙過海：任一玩家集齊八朵花 → 自摸結束
        for candidate, fset in enumerate(self._flower_sets):
            if len(fset) == N_FLOWERS:
                win_tile = tile if candidate == pid else None
                self._resolve_flower_win(
                    winner_pid=candidate,
                    loser_pid=candidate,
                    win_tile=win_tile,
                    flower_type="ba_xian",
                    win_source="TSUMO",
                )
                return True

        # 七搶一：有玩家集齊七朵花，最後一朵在其他人身上
        for candidate, fset in enumerate(self._flower_sets):
            if len(fset) == N_FLOWERS - 1:
                missing = list(self._flower_union - fset)
                if not missing:
                    continue
                holder_pid, held_tile = self._find_flower_holder(missing[0])
                if holder_pid is None:
                    continue
                self._resolve_flower_win(
                    winner_pid=candidate,
                    loser_pid=holder_pid,
                    win_tile=held_tile,
                    flower_type="qi_qiang_yi",
                    win_source="RON",
                )
                return True

        return False

    def _draw_into_hand(self, pid: int):
        """Draw from wall into hand, auto‑handling flowers (replacing immediately)."""
        while self._can_draw_from_wall():
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                if self._register_flower(pid, t):
                    return
                continue
            self.players[pid]["hand"].append(t)
            break

    def _draw_to_drawn(self, pid: int):
        """Draw from wall into the `drawn` slot, replacing flowers immediately."""
        self.players[pid]["drawn"] = None
        while self._can_draw_from_wall():
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                if self._register_flower(pid, t):
                    return
                continue
            self.players[pid]["drawn"] = t
            break

    def _legal_discards(self, pid: int):
        """Return list of tile ids in hand that can be legally discarded (non‑flower)."""
        from .tiles import is_flower  # 重新導入以防循環
        return [t for t in self.players[pid]["hand"] if not is_flower(t)]

    def _resolve_claims(self) -> Optional[Dict[str, Any]]:
        """Resolve reaction claims by priority and distance; return chosen claim or None."""
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

    def _obs(self, pid: int) -> Observation:
        """Build the observation for a given player id, including public info and legal actions."""
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
