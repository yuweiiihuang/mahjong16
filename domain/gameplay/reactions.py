"""Reaction handling helpers for Mahjong environment."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..tiles import chi_options
from ..rules.hands import is_win_16
from .game_types import Action, Observation

PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}


class ReactionMixin:
    """Encapsulate post-discard reaction windows."""

    def pending_reactions(self) -> List[int]:
        """Return unanswered seats; choices are private until the window resolves."""
        if self.phase != "REACTION":
            return []
        return [pid for pid in self.reaction_queue[self.reaction_idx:]
                if pid not in self.reaction_responses]

    def _reaction_phase_actions(
        self, pid: Optional[int] = None, include_submitted: bool = False
    ) -> List[Action]:
        if not self.reaction_queue or not (0 <= self.reaction_idx < len(self.reaction_queue)):
            return []
        actor = self.reaction_queue[self.reaction_idx] if pid is None else pid
        if actor not in self.pending_reactions() and not (
            include_submitted and actor in self.reaction_responses
        ):
            return []
        acts: List[Action] = [{"type": "PASS"}]
        discard = self.last_discard
        if discard is None:
            return acts
        tile = discard["tile"]
        player_state = self.players[actor]
        from_upstream = (self._seat_index.get(actor)
                         == (self._seat_index.get(discard["pid"], -999) + 1)
                         % self.rules.n_players)
        ting_locked = bool(getattr(player_state, "declared_ting", False))
        if self.qiang_gang_mode:
            if self.rules.allow_hu and is_win_16(player_state.hand + [tile], player_state.melds, self.rules):
                acts.append({"type": "HU"})
            return acts
        if (
            (not ting_locked)
            and from_upstream
            and self.rules.allow_chi
        ):
            for a, b in chi_options(tile, player_state.hand):
                acts.append({"type": "CHI", "use": [a, b]})
        if (not ting_locked) and self.rules.allow_pong and player_state.hand.count(tile) >= 2:
            acts.append({"type": "PONG"})
        if ((not ting_locked) and self.rules.allow_gang and player_state.hand.count(tile) >= 3
                and (not from_upstream or self.rules.allow_upstream_gang)):
            acts.append({"type": "GANG"})
        if self.rules.allow_hu and is_win_16(player_state.hand + [tile], player_state.melds, self.rules):
            acts.append({"type": "HU"})
        return acts

    def _handle_reaction_action(
        self, action: Action, pid: Optional[int] = None
    ) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        assert self.reaction_queue and 0 <= self.reaction_idx < len(self.reaction_queue), "reaction queue empty"
        if pid is None:
            pid = self.reaction_queue[self.reaction_idx]
        assert action in self.legal_actions(pid), "非法或已回應的操作"
        assert pid in self.pending_reactions(), "玩家已回應或不在反應視窗"
        a_type = action.get("type")
        assert a_type in ("PASS", "CHI", "PONG", "GANG", "HU"), "反應期僅允許 PASS/CHI/PONG/GANG/HU"
        if self.players[pid].declared_ting and a_type not in ("PASS", "HU"):
            a_type = "PASS"
        if a_type != "PASS":
            claim: Dict[str, Any] = {"pid": pid, "type": a_type}
            dist = (self._seat_index.get(pid, 0) - self._seat_index.get(self.last_discard["pid"], 0)) % self.rules.n_players
            if dist == 0:
                dist = self.rules.n_players
            claim["distance"] = dist
            claim["priority"] = PRIORITY[a_type]
            if a_type == "CHI":
                use = action.get("use")
                assert isinstance(use, list) and len(use) == 2, "CHI 需指定兩張手牌"
                claim["use"] = use
            self.claims.append(claim)
        self.reaction_responses[pid] = dict(action, type=a_type)
        while (self.reaction_idx < len(self.reaction_queue)
               and self.reaction_queue[self.reaction_idx] in self.reaction_responses):
            self.reaction_idx += 1
        best = self._resolve_claims()
        if best is not None:
            best_rank = (-best["priority"], best["distance"], best["pid"])
            can_change = False
            for candidate in self.pending_reactions():
                distance = (self._seat_index[candidate]
                            - self._seat_index[self.last_discard["pid"]]) % self.rules.n_players
                if any((-PRIORITY[a["type"]], distance, candidate) < best_rank
                       for a in self._reaction_phase_actions(candidate) if a["type"] != "PASS"):
                    can_change = True
                    break
            if not can_change:
                return self._resolve_reaction_window()
        if self.reaction_idx < len(self.reaction_queue):
            next_pid = self.reaction_queue[self.reaction_idx]
            return self._obs(next_pid), [0] * self.rules.n_players, False, {}
        return self._resolve_reaction_window()

    def _resolve_reaction_window(self) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        resolved = self._resolve_claims()
        self.claims = []
        if resolved is None:
            if self.qiang_gang_mode and self.pending_kakan:
                return self._complete_pending_kakan()
            return self._advance_after_no_claims()
        return self._apply_claim_resolution(resolved)

    def _complete_pending_kakan(self) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        assert self.pending_kakan is not None
        kpid = self.pending_kakan["pid"]
        ktile = self.pending_kakan["tile"]
        me = self.players[kpid]
        if me.drawn == ktile:
            me.drawn = None
        else:
            me.hand.remove(ktile)
        for meld in (me.melds or []):
            if (meld.get("type") or "").upper() == "PONG" and (meld.get("tiles") or [None])[0] == ktile:
                meld["type"] = "KAKAN"
                meld["tiles"] = [ktile, ktile, ktile, ktile]
                break
        self.n_gang += 1
        self.qiang_gang_mode = False
        self.pending_kakan = None
        self.turn = kpid
        self.phase = "TURN"
        self._draw_to_drawn(kpid)
        self._recent_gang_draw_pid = kpid
        self.last_discard = None
        if self.players[kpid].drawn is None:
            self.done = True
            rewards = [0] * self.rules.n_players
            return self._obs(self.turn), rewards, True, {}
        return self._obs(self.turn), [0] * self.rules.n_players, False, {}

    def _advance_after_no_claims(self) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        self.phase = "TURN"
        base_idx = self._seat_index.get(self.last_discard["pid"], 0)
        self.turn = self.seating_order[(base_idx + 1) % self.rules.n_players]
        self.players[self.turn].pong_waiting_draw = False
        self._draw_to_drawn(self.turn)
        if self.players[self.turn].drawn is None:
            self.done = True
            rewards = [0] * self.rules.n_players
            return self._obs(self.turn), rewards, True, {}
        return self._obs(self.turn), [0] * self.rules.n_players, False, {}

    def _apply_claim_resolution(self, resolved: Dict[str, Any]) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        claimer = resolved["pid"]
        ctype = resolved["type"]
        discarder = self.last_discard["pid"]
        tile = self.last_discard["tile"]
        self._remove_claimed_discard(discarder, tile)
        self.last_discard = None
        if ctype == "CHI":
            return self._resolve_claim_chi(claimer, discarder, tile, resolved)
        if ctype == "PONG":
            return self._resolve_claim_pong(claimer, discarder, tile)
        if ctype == "GANG":
            return self._resolve_claim_gang(claimer, discarder, tile)
        return self._resolve_claim_hu(claimer, discarder, tile)

    def _resolve_claim_chi(
        self, claimer: int, discarder: int, tile: int, resolved: Dict[str, Any]
    ) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        use = resolved.get("use")
        assert isinstance(use, list) and len(use) == 2, "CHI 需指定兩張手牌"
        self.players[claimer].hand.remove(use[0])
        self.players[claimer].hand.remove(use[1])
        self.players[claimer].melds.append({"type": "CHI", "tiles": [use[0], use[1], tile], "from_pid": discarder})
        self._public_live_consume([use[0], use[1]])
        self.total_open_melds += 1
        self.players[claimer].drawn = None
        if not self.rules.allow_same_tile_discard_after_chi:
            self.players[claimer].chi_discard_lock = tile
        self.turn = claimer
        self.phase = "TURN"
        info = {"resolved_claim": {"pid": claimer, "type": "CHI", "tile": tile, "from_pid": discarder, "use": list(use)}}
        return self._obs(self.turn), [0] * self.rules.n_players, False, info

    def _resolve_claim_pong(
        self, claimer: int, discarder: int, tile: int
    ) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        for _ in range(2):
            self.players[claimer].hand.remove(tile)
        self.players[claimer].melds.append({"type": "PONG", "tiles": [tile, tile, tile], "from_pid": discarder})
        self._public_live_decrement(tile, amount=2)
        self.total_open_melds += 1
        self.players[claimer].drawn = None
        if not self.rules.allow_immediate_kakan_after_pong:
            self.players[claimer].pong_waiting_draw = True
        self.turn = claimer
        self.phase = "TURN"
        info = {"resolved_claim": {"pid": claimer, "type": "PONG", "tile": tile, "from_pid": discarder}}
        return self._obs(self.turn), [0] * self.rules.n_players, False, info

    def _resolve_claim_gang(
        self, claimer: int, discarder: int, tile: int
    ) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        for _ in range(3):
            self.players[claimer].hand.remove(tile)
        self.players[claimer].melds.append({"type": "GANG", "tiles": [tile, tile, tile, tile], "from_pid": discarder})
        self._public_live_decrement(tile, amount=3)
        self.total_open_melds += 1
        self.n_gang += 1
        self.players[claimer].drawn = None
        self.turn = claimer
        self.phase = "TURN"
        info = {"resolved_claim": {"pid": claimer, "type": "GANG", "tile": tile, "from_pid": discarder}}
        self._draw_to_drawn(self.turn)
        if self.players[self.turn].drawn is None:
            self.done = True
            rewards = [0] * self.rules.n_players
            return self._obs(self.turn), rewards, True, info
        return self._obs(self.turn), [0] * self.rules.n_players, False, info

    def _resolve_claim_hu(
        self, claimer: int, discarder: int, tile: int
    ) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        self.win_tile = tile
        self.win_source = "RON"
        self.winner = claimer
        self.turn_at_win = discarder
        self.winner_is_dealer = (claimer == getattr(self, "dealer_pid", 0))
        if self.qiang_gang_mode:
            self.win_by_qiang_gang = True
        self.qiang_gang_mode = False
        self.pending_kakan = None
        self.phase = "DONE"
        self.reaction_queue = []
        self.reaction_idx = 0
        self.done = True
        info = {"resolved_claim": {"pid": claimer, "type": "HU", "tile": tile, "from_pid": discarder}}
        rewards = [0] * self.rules.n_players
        return self._obs(self.turn), rewards, True, info

    def _remove_claimed_discard(self, discarder: int, tile: int) -> None:
        rv = self.players[discarder].river
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

    def _resolve_claims(self) -> Optional[Dict[str, Any]]:
        if not self.claims:
            return None
        hu_claims = [c for c in self.claims if c["type"] == "HU"]
        if hu_claims:
            hu_claims.sort(key=lambda c: (c["distance"], c["pid"]))
            return hu_claims[0]
        self.claims.sort(key=lambda c: (-c["priority"], c["distance"], c["pid"]))
        return self.claims[0]


__all__ = ["ReactionMixin", "PRIORITY"]
