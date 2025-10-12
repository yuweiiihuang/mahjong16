from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from domain import Mahjong16Env, Ruleset


WINDS = ["E", "S", "W", "N"]


def _next_wind(w: str) -> str:
    try:
        i = WINDS.index(w)
        return WINDS[(i + 1) % 4]
    except Exception:
        return "E"


@dataclass
class TableState:
    quan_feng: str = "E"            # E -> S -> W -> N -> E ...
    seat_winds: List[str] = None     # length n_players; mapping pid->'E'/'S'/'W'/'N'
    seating_order: List[int] = None  # length n_players; circular order of pids (index 0 = East)
    dealer_pid: int = 0
    dealer_streak: int = 0           # 連莊次数（起手 0 表示 2*0+1 台）
    dealer_pass_count: int = 0       # 計算本圈已經『下莊次數』（達 n_players 代表過一圈）
    jang_count: int = 0              # 已完成的「將」數（四圈結束後 +1）


class TableManager:
    """Lightweight match/table manager for multi‑hand flow.

    Responsibilities:
      - Randomize initial seating (seat_winds) and dealer, independently.
      - Start each hand with current quan_feng / dealer / dealer_streak.
      - On hand end: 連莊 → streak+1; 下莊 → rotate dealer to next pid, reset streak, pass_count+1.
      - After pass_count reaches n_players → bump quan_feng; when it wraps back to 'E', re‑randomize seating.
    """

    def __init__(self, rules: Ruleset, seed: Optional[int] = None):
        import random
        self.rules = rules
        self.rng = random.Random(seed)
        self.state = TableState()

    def _random_seating(self, n_players: int) -> List[int]:
        # 產生一個完整打亂的座次順序（依圓桌順時針），索引0位置代表東
        order = list(range(n_players))
        self.rng.shuffle(order)
        return order

    def _winds_from_seating(self, seating_order: List[int], n_players: int) -> List[str]:
        # 將 ESWN 順序依 seating_order 指派給 pid，回傳 pid->wind 的映射表
        winds_map = [None] * n_players
        for i, pid in enumerate(seating_order):
            winds_map[pid] = WINDS[i]
        return winds_map

    def initialize(self, n_players: int):
        self.state.quan_feng = "E"
        # 隨機完整打亂座次；索引0代表東、1南、2西、3北
        self.state.seating_order = self._random_seating(n_players)
        # 依座次給風位；莊家為東（座次索引0）
        self.state.seat_winds = self._winds_from_seating(self.state.seating_order, n_players)
        self.state.dealer_pid = self.state.seating_order[0]
        self.state.dealer_streak = 0
        self.state.dealer_pass_count = 0
        self.state.jang_count = 0

    def start_hand(self, env: Mahjong16Env):
        """Preset env for the next hand and reset it."""
        # Ensure initialized
        if not self.state.seat_winds:
            self.initialize(env.rules.n_players)
        # Preset state into env, then reset
        env.preset_seat_winds = list(self.state.seat_winds)
        env.preset_dealer_pid = int(self.state.dealer_pid)
        env.preset_quan_feng = str(self.state.quan_feng)
        env.preset_dealer_streak = int(self.state.dealer_streak)
        return env.reset()

    def finish_hand(self, env: Mahjong16Env):
        """Update table state after a hand finishes (win or flow)."""
        winner = getattr(env, "winner", None)
        dealer = getattr(env, "dealer_pid", 0)
        n_players = env.rules.n_players
        if winner is None or winner == dealer:
            # 連莊（含流局）：莊家續做，streak +1
            self.state.dealer_streak += 1
        else:
            # 下莊：由下家上莊（依 seating_order 的下一位）
            if self.state.seating_order and dealer in self.state.seating_order:
                idx = self.state.seating_order.index(dealer)
                self.state.dealer_pid = self.state.seating_order[(idx + 1) % n_players]
            else:
                self.state.dealer_pid = (dealer + 1) % n_players
            self.state.dealer_streak = 0
            self.state.dealer_pass_count += 1
            # 過一圈（四人都做過莊一次）→ 圈風推進
            if self.state.dealer_pass_count >= n_players:
                self.state.dealer_pass_count = 0
                self.state.quan_feng = _next_wind(self.state.quan_feng)
                # 回到東圈 → 重新抽座位（門風更新，完整打亂相對座次）
                if self.state.quan_feng == "E":
                    self.state.jang_count += 1
                    self.state.seating_order = self._random_seating(n_players)
                    self.state.seat_winds = self._winds_from_seating(self.state.seating_order, n_players)
                    # 新東圈起莊為東（座次索引0）
                    self.state.dealer_pid = self.state.seating_order[0]
