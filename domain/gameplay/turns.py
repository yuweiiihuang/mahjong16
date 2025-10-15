"""Turn-phase helpers for the Mahjong environment."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..tiles import is_flower
from ..rules.hands import is_win_16, waits_after_discard_17
from .game_types import Action, Observation

if TYPE_CHECKING:
    from .flowers import FlowerOutcome


class TurnLoopMixin:
    """Encapsulate the draw/discard loop for the environment."""

    def _turn_phase_actions(self, pid: Optional[int] = None) -> List[Action]:
        if pid is None:
            pid = self.turn
        me = self.players[pid]
        acts: List[Action] = []
        if self._tsumo_available(pid):
            acts.append({"type": "HU", "source": "TSUMO"})
        if me.drawn is not None:
            acts.append({"type": "DISCARD", "tile": me.drawn, "from": "drawn"})
        declared_ting = bool(getattr(me, "declared_ting", False))
        if not declared_ting:
            for tile in self._legal_discards(pid):
                acts.append({"type": "DISCARD", "tile": tile, "from": "hand"})
            acts.extend(self._ting_candidates(pid))
        if self.rules.allow_gang:
            for tile in self._angang_candidates(pid):
                acts.append({"type": "ANGANG", "tile": tile})
            for tile in self._kakan_candidates(pid):
                acts.append({"type": "KAKAN", "tile": tile})
        return acts

    def _handle_turn_action(self, action: Action) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        pid = self.turn
        a_type = action.get("type")
        if a_type == "HU":
            return self._apply_tsumo(pid)
        if a_type == "ANGANG":
            return self._apply_angang(pid, action)
        if a_type == "KAKAN":
            return self._apply_kakan(pid, action)
        if a_type in ("DISCARD", "TING"):
            return self._apply_discards(pid, action)
        raise AssertionError("本階段僅能丟牌/自摸/宣告聽/暗槓/加槓")

    def _apply_tsumo(self, pid: int) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        me = self.players[pid]
        assert me.drawn is not None, "自摸需有當前摸牌"
        self.winner = pid
        self.win_source = "TSUMO"
        self.win_tile = me.drawn
        self.turn_at_win = pid
        self.winner_is_dealer = (pid == getattr(self, "dealer_pid", 0))
        if self._recent_gang_draw_pid == pid:
            self.win_by_gang_draw = True
        self.phase = "DONE"
        self.reaction_queue = []
        self.reaction_idx = 0
        self.last_discard = None
        self.done = True
        rewards = [0] * self.rules.n_players
        return self._obs(self.turn), rewards, True, {}

    def _apply_discards(self, pid: int, action: Action) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        a_type = action.get("type")
        src = action.get("from", "hand")
        tile = action["tile"]
        if a_type == "TING":
            valid = any(
                candidate["tile"] == tile and candidate.get("from") == src
                for candidate in self._ting_candidates(pid)
            )
            assert valid, "宣告聽需指定合法棄牌"
        if src == "drawn":
            assert self.players[pid].drawn == tile, "丟牌來源為 drawn，但牌不相符"
            self.players[pid].drawn = None
        else:
            assert tile in self.players[pid].hand and (not is_flower(tile)), "非法丟手牌"
            self.players[pid].hand.remove(tile)
            if self.players[pid].drawn is not None:
                self.players[pid].hand.append(self.players[pid].drawn)
                self.players[pid].drawn = None
        self.players[pid].river.append(tile)
        self.discard_pile.append(tile)
        self.discard_count += 1
        self.last_discard = {"pid": pid, "tile": tile}
        self._public_live_decrement(tile)
        if a_type == "TING":
            self.players[pid].declared_ting = True
            self.players[pid].ting_declared_at = self.discard_count
            self.players[pid].ting_declared_open_melds = self.total_open_melds
        self.phase = "REACTION"
        self.reaction_queue = [
            self.seating_order[(self._seat_index.get(pid, 0) + i) % self.rules.n_players]
            for i in (1, 2, 3)
        ]
        self.reaction_idx = 0
        self.claims = []
        self._recent_gang_draw_pid = None
        next_pid = self.reaction_queue[self.reaction_idx]
        return self._obs(next_pid), [0] * self.rules.n_players, False, {}

    def _apply_angang(self, pid: int, action: Action) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        tile = action.get("tile")
        assert tile in self._angang_candidates(pid), "暗槓需手牌+摸牌共4張同牌"
        me = self.players[pid]
        removed = 0
        while removed < 4 and tile in me.hand:
            me.hand.remove(tile)
            removed += 1
        if removed < 4 and me.drawn == tile:
            me.drawn = None
            removed += 1
        while removed < 4 and tile in me.hand:
            me.hand.remove(tile)
            removed += 1
        assert removed == 4
        me.melds.append({"type": "ANGANG", "tiles": [tile, tile, tile, tile], "from_pid": None})
        self._public_live_decrement(tile, amount=4)
        self.n_gang += 1
        self._draw_to_drawn(pid)
        self._recent_gang_draw_pid = pid
        if self.players[pid].drawn is None:
            self.done = True
            rewards = [0] * self.rules.n_players
            return self._obs(self.turn), rewards, True, {}
        return self._obs(self.turn), [0] * self.rules.n_players, False, {}

    def _apply_kakan(self, pid: int, action: Action) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        tile = action.get("tile")
        assert tile in self._kakan_candidates(pid), "加槓需已有 PONG 且持有第4張"
        self.qiang_gang_mode = True
        self.pending_kakan = {"pid": pid, "tile": tile}
        self.last_discard = {"pid": pid, "tile": tile}
        self._public_live_decrement(tile)
        self.phase = "REACTION"
        self.reaction_queue = [
            self.seating_order[(self._seat_index.get(pid, 0) + i) % self.rules.n_players]
            for i in (1, 2, 3)
        ]
        self.reaction_idx = 0
        self.claims = []
        next_pid = self.reaction_queue[self.reaction_idx]
        return self._obs(next_pid), [0] * self.rules.n_players, False, {}

    def _tsumo_available(self, pid: int) -> bool:
        if not self.rules.allow_hu:
            return False
        me = self.players[pid]
        if me.drawn is None:
            return False
        return is_win_16(me.hand + [me.drawn], me.melds, self.rules)

    def _angang_candidates(self, pid: int) -> List[int]:
        if not self.rules.allow_gang:
            return []
        me = self.players[pid]
        all_tiles = list(me.hand) + ([me.drawn] if me.drawn is not None else [])
        seen: List[int] = []
        for tile in all_tiles:
            if tile not in seen:
                seen.append(tile)
        return [tile for tile in seen if not is_flower(tile) and all_tiles.count(tile) >= 4]

    def _kakan_candidates(self, pid: int) -> List[int]:
        if not self.rules.allow_gang:
            return []
        me = self.players[pid]
        pong_bases: List[int] = []
        for meld in (me.melds or []):
            if (meld.get("type") or "").upper() == "PONG":
                tiles_m = list(meld.get("tiles") or [])
                if tiles_m:
                    base = tiles_m[0]
                    if base not in pong_bases:
                        pong_bases.append(base)
        if not pong_bases:
            return []
        all_tiles = list(me.hand) + ([me.drawn] if me.drawn is not None else [])
        return [base for base in pong_bases if all_tiles.count(base) >= 1]

    def _ting_candidates(self, pid: int) -> List[Action]:
        if self.players[pid].declared_ting or not self.rules.allow_ting:
            return []
        me = self.players[pid]
        drawn = me.drawn
        melds = me.melds or []
        candidates: List[Action] = []
        for tile in list(self._legal_discards(pid)):
            waits = waits_after_discard_17(me.hand, drawn, melds, tile, "hand", self.rules)
            if waits:
                candidates.append({"type": "TING", "tile": tile, "from": "hand", "waits": waits})
        if drawn is not None:
            waits = waits_after_discard_17(me.hand, drawn, melds, drawn, "drawn", self.rules)
            if waits:
                candidates.append({"type": "TING", "tile": drawn, "from": "drawn", "waits": waits})
        return candidates

    def _handle_flower_draw(self, pid: int, tile: int) -> bool:
        outcome = self._flower_manager.register_flower(
            pid=pid,
            tile=tile,
            players=self.players,
            round_done=getattr(self, "done", False),
        )
        return self._apply_flower_outcome(outcome)

    def _apply_flower_outcome(self, outcome: "FlowerOutcome") -> bool:
        if outcome.is_win:
            if outcome.winner_pid is None or outcome.flower_type is None or outcome.win_source is None:
                raise ValueError("FlowerOutcome missing data for win resolution")
            self._resolve_flower_win(
                winner_pid=outcome.winner_pid,
                loser_pid=outcome.loser_pid,
                win_tile=outcome.win_tile,
                flower_type=outcome.flower_type,
                win_source=outcome.win_source,
            )
        return outcome.round_ended

    def _register_flower(self, pid: int, tile: int) -> bool:
        return self._handle_flower_draw(pid, tile)

    def _draw_into_hand(self, pid: int) -> None:
        while self._can_draw_from_wall():
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                if self._handle_flower_draw(pid, t):
                    return
                continue
            self.players[pid].hand.append(t)
            break

    def _draw_to_drawn(self, pid: int) -> None:
        self.players[pid].drawn = None
        while self._can_draw_from_wall():
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                if self._handle_flower_draw(pid, t):
                    return
                continue
            self.players[pid].drawn = t
            break

    def _legal_discards(self, pid: int) -> List[int]:
        return [t for t in self.players[pid].hand if not is_flower(t)]


__all__ = ["TurnLoopMixin"]
