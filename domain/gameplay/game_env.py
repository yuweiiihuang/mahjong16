"""Mahjong environment facade composed from gameplay modules."""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from ..tiles import N_TILES
from ..rules.ruleset import Ruleset
from .game_types import Action, Observation
from ..table.deal import TableSetupMixin
from .reactions import ReactionMixin
from .turns import TurnLoopMixin


class MahjongEnvironment(TableSetupMixin, ReactionMixin, TurnLoopMixin):
    """Taiwan 16-tile Mahjong single-table environment."""

    def __init__(self, rules: Ruleset, seed: Optional[int] = None):
        self.rules = rules
        self.rng = random.Random(seed)
        self.reset_rng_seed = seed
        self._public_live: List[int] = [4] * N_TILES

    # ====== 尾牌留置（流局）判斷 ======
    def _dead_wall_reserved(self) -> int:
        mode = getattr(self.rules, "dead_wall_mode", "fixed")
        base = getattr(self.rules, "dead_wall_base", 16)
        if mode == "gang_plus_one":
            return base + getattr(self, "n_gang", 0)
        return base

    def _can_draw_from_wall(self) -> bool:
        return len(self.wall) > self._dead_wall_reserved()

    # ====== API ======
    def reset(self) -> Observation:
        self._reset_round_state()
        self._assign_seats_and_dealer()
        self._deal_initial_hands()
        return self._obs(self.turn)

    def legal_actions(self, pid: Optional[int] = None) -> List[Action]:
        if getattr(self, "done", False):
            return []
        if self.phase == "TURN":
            target = self.turn if pid is None else pid
            return self._turn_phase_actions(target)
        return self._reaction_phase_actions(pid)

    def step(self, action: Action) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        assert not self.done, "episode is done"
        if self.phase == "TURN":
            return self._handle_turn_action(action)
        return self._handle_reaction_action(action)

    # ====== 內部輔助 ======
    def _resolve_flower_win(
        self,
        winner_pid: int,
        loser_pid: int | None,
        win_tile: int | None,
        flower_type: str,
        win_source: str,
    ) -> None:
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

    def _obs(self, pid: int) -> Observation:
        me = self.players[pid]
        is_done = getattr(self, "done", False)
        obs: Observation = {
            "player": pid,
            "phase": self.phase,
            "hand": list(me.hand),
            "drawn": me.drawn,
            "flowers": list(me.flowers),
            "melds": [m if isinstance(m, dict) else list(m) for m in me.melds],
            "declared_ting": bool(getattr(me, "declared_ting", False)),
            "melds_all": [[m if isinstance(m, dict) else list(m) for m in p.melds] for p in self.players],
            "rivers": [list(p.river) for p in self.players],
            "live_public": self._public_live_counts(),
            "n_remaining": len(self.wall),
            "last_discard": dict(self.last_discard) if self.last_discard else None,
            "legal_actions": ([] if is_done else self.legal_actions(pid=None if self.phase == "TURN" else pid)),
        }
        return obs

    def _init_public_live_counts(self) -> None:
        self._public_live = [4] * N_TILES

    def _public_live_counts(self) -> List[int]:
        return list(self._public_live)

    def _public_live_decrement(self, tile: int, amount: int = 1) -> None:
        if amount <= 0:
            return
        if 0 <= tile < N_TILES:
            current = self._public_live[tile]
            if current <= 0:
                return
            self._public_live[tile] = max(0, current - amount)

    def _public_live_consume(self, tiles: List[int]) -> None:
        for tile in tiles:
            if tile is None:
                continue
            self._public_live_decrement(int(tile))


Mahjong16Env = MahjongEnvironment

__all__ = ["MahjongEnvironment", "Mahjong16Env"]
