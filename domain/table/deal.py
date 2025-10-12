"""Table setup helpers for Mahjong environment lifecycle."""
from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from random import Random
    from ..rules.ruleset import Ruleset

from ..tiles import full_wall
from ..gameplay.flowers import FlowerManager
from ..gameplay.player_state import PlayerState


class TableSetupMixin:
    """Mixin providing seat assignment and round bootstrap helpers."""

    rules: "Ruleset"
    rng: "Random"

    def _reset_round_state(self) -> None:
        """Clear prior round bookkeeping and reinitialize mutable table state."""

        self.wall = full_wall(self.rules.include_flowers, self.rng)
        self.discard_pile = []
        self.discard_count = 0
        self.total_open_melds = 0
        self.flower_win_type = None
        self._flower_manager = FlowerManager(
            n_players=self.rules.n_players,
            enable_flower_wins=getattr(self.rules, "enable_flower_wins", True),
        )
        self.players = [PlayerState(id=i) for i in range(self.rules.n_players)]
        self.n_gang = 0
        self.reaction_queue = []
        self.reaction_idx = 0
        self.claims = []
        self.last_discard = None
        self.done = False
        self.winner = None
        self.win_source = None
        self.win_tile = None
        self.turn_at_win = None
        self.win_by_gang_draw = False
        self.win_by_qiang_gang = False
        self._recent_gang_draw_pid = None
        self.qiang_gang_mode = False
        self.pending_kakan = None
        self._init_public_live_counts()

    def _assign_seats_and_dealer(self) -> None:
        """Determine seat winds, seating order, and dealer selection for the round."""

        winds_cycle = ["E", "S", "W", "N"]
        preset_winds: Optional[List[str]] = getattr(self, "preset_seat_winds", None)
        if isinstance(preset_winds, list) and len(preset_winds) == self.rules.n_players:
            self.seat_winds = list(preset_winds)
        else:
            if getattr(self.rules, "randomize_seating_and_dealer", False):
                order = list(range(self.rules.n_players))
                self.rng.shuffle(order)
                winds = [None] * self.rules.n_players
                for i, pid in enumerate(order):
                    winds[pid] = winds_cycle[i]
                self.seat_winds = winds
            else:
                self.seat_winds = winds_cycle[: self.rules.n_players]

        try:
            order_map: Dict[str, int] = {w: i for i, w in enumerate(winds_cycle)}
            pairs = [(order_map.get(w, 99), pid) for pid, w in enumerate(self.seat_winds)]
            pairs.sort()
            self.seating_order = [pid for rank, pid in pairs if rank != 99]
        except Exception:
            self.seating_order = list(range(self.rules.n_players))
        self._seat_index = {pid: i for i, pid in enumerate(self.seating_order)}

        preset_dealer_pid = getattr(self, "preset_dealer_pid", None)
        if isinstance(preset_dealer_pid, int) and 0 <= preset_dealer_pid < self.rules.n_players:
            self.dealer_pid = int(preset_dealer_pid)
        else:
            self.dealer_pid = self.seating_order[0] if self.seating_order else 0

        self.quan_feng = (
            getattr(self, "preset_quan_feng", None)
            or getattr(self, "quan_feng", "E")
            or "E"
        )
        dealer_streak = getattr(self, "preset_dealer_streak", None)
        self.dealer_streak = int(dealer_streak) if isinstance(dealer_streak, int) else 0
        self.winner_is_dealer = False
        self.turn = self.dealer_pid
        self.phase = "TURN"

    def _deal_initial_hands(self) -> None:
        """Distribute initial concealed tiles and draw the dealer's starting tile."""

        order_pids = list(self.seating_order) if getattr(self, "seating_order", None) else list(range(self.rules.n_players))
        for _ in range(self.rules.initial_hand):
            for pid in order_pids:
                self._draw_into_hand(pid)
                if getattr(self, "done", False):
                    break
            if getattr(self, "done", False):
                break

        if not getattr(self, "done", False):
            self._draw_to_drawn(self.dealer_pid)


__all__ = ["TableSetupMixin"]
