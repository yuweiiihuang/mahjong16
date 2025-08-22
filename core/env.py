
from __future__ import annotations
from typing import List, Dict, Any, Optional
import random

from .tiles import full_wall, is_flower, N_TILES, N_FLOWERS, tile_to_str, hand_to_str
from .ruleset import Ruleset
from .judge import is_win_16, settle_scores_stub

class Mahjong16Env:
    """
    台麻16簡化環境（加入 drawn 語義）：
    - 每家持有 16 張手牌；輪到該家時，摸到 1 張置於 `drawn`（臨時第17張），再丟回 1 張。
    - 發牌後莊家（P0）先多摸一張至 `drawn`（開門 17 張）。
    - 支援：發牌、摸牌（含補花）、丟牌。
    - TODO：吃/碰/槓/胡、計分（保留接口）。
    """
    def __init__(self, rules: Ruleset, seed: Optional[int]=None):
        self.rules = rules
        self.rng = random.Random(seed)
        self.reset_rng_seed = seed

    # ====== API ======
    def reset(self) -> Dict[str, Any]:
        self.wall: List[int] = full_wall(self.rules.include_flowers, self.rng)
        self.discard_pile: List[int] = []
        self.players: List[Dict[str, Any]] = [self._new_player(i) for i in range(self.rules.n_players)]
        self.turn = 0  # 莊家

        # 發牌：每家 16 張（補花到非花）；此處直接放入手牌
        for _ in range(self.rules.initial_hand):
            for pid in range(self.rules.n_players):
                self._draw_into_hand(pid)

        # 莊家先摸一張至 drawn（16+drawn=17）
        self._draw_to_drawn(0)

        self.last_discard: Optional[Dict[str, Any]] = None
        self.done = False
        self.winner: Optional[int] = None

        return self._obs(self.turn)

    def legal_actions(self, pid: Optional[int]=None) -> List[Dict[str, Any]]:
        pid = self.turn if pid is None else pid
        me = self.players[pid]
        acts: List[Dict[str, Any]] = []
        if me["drawn"] is not None:
            acts.append({"type":"DISCARD", "tile": me["drawn"], "from":"drawn"})
        for t in self._legal_discards(pid):
            acts.append({"type":"DISCARD", "tile": t, "from":"hand"})
        # TODO：吃/碰/槓/自摸/榮胡
        acts.append({"type":"PASS"})
        return acts

    def step(self, action: Dict[str, Any]):
        assert not self.done, "episode is done"
        pid = self.turn

        a_type = action.get("type")
        if a_type == "DISCARD":
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

            self.players[pid]["river"].append(tile)
            self.discard_pile.append(tile)
            self.last_discard = {"pid": pid, "tile": tile}

            self.turn = (self.turn + 1) % self.rules.n_players
            self._draw_to_drawn(self.turn)

        elif a_type == "PASS":
            raise AssertionError("本簡化版在自己回合不可 PASS；僅預留反應視窗用")
        else:
            raise NotImplementedError(f"action type not supported yet: {a_type}")

        for pid2 in range(self.rules.n_players):
            if is_win_16(self.players[pid2]["hand"], self.players[pid2]["melds"], self.rules):
                self.done = True
                self.winner = pid2
                break

        if len(self.wall) == 0:
            self.done = True  # 牆摸完流局

        rewards = [0]*self.rules.n_players
        if self.done:
            rewards = settle_scores_stub(self)

        return self._obs(self.turn), rewards, self.done, {}

    # ====== helpers ======
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
        while self.wall:
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                self.players[pid]["flowers"].append(t)
                continue
            self.players[pid]["hand"].append(t)
            break

    def _draw_to_drawn(self, pid: int):
        self.players[pid]["drawn"] = None
        while self.wall:
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                self.players[pid]["flowers"].append(t)
                continue
            self.players[pid]["drawn"] = t
            break

    def _legal_discards(self, pid: int):
        return [t for t in self.players[pid]["hand"] if not is_flower(t)]

    def _obs(self, pid: int) -> Dict[str, Any]:
        me = self.players[pid]
        return {
            "player": pid,
            "hand": list(me["hand"]),
            "drawn": me["drawn"],
            "flowers": list(me["flowers"]),
            "melds": [list(m) for m in me["melds"]],
            "rivers": [list(p["river"]) for p in self.players],
            "n_remaining": len(self.wall),
            "last_discard": dict(self.last_discard) if self.last_discard else None,
            "legal_actions": self.legal_actions(pid),
        }
