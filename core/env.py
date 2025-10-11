# file: core/env.py
from __future__ import annotations
from typing import Iterable, List, Dict, Any, Optional, Tuple
import random

from .tiles import (
    N_TILES,
    chi_options,
    full_wall,
    hand_to_str,
    is_flower,
    tile_to_str,
)
from .ruleset import Ruleset
from .hand import is_win_16, waits_after_discard_17
from .types import Action, Observation
from .state import PlayerState
from .flowers import FlowerManager, FlowerOutcome

# 反應優先權：胡 > 槓 > 碰 > 吃
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}


def _iter_public_meld_tiles(meld: Dict[str, Any] | Iterable[int]) -> Iterable[int]:
    """Yield tile ids that are visible from a meld structure."""

    tiles: Iterable[int]
    if isinstance(meld, dict):
        tiles = meld.get("tiles") or []
    else:
        tiles = meld

    for tile in tiles:
        if tile is None:
            continue
        value = int(tile)
        if 0 <= value < N_TILES:
            yield value

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
        self._reset_round_state()
        self._assign_seats_and_dealer()
        self._deal_initial_hands()
        return self._obs(self.turn)

    def _reset_round_state(self) -> None:
        """Clear prior round bookkeeping and reinitialize mutable table state."""
        self.wall: List[int] = full_wall(self.rules.include_flowers, self.rng)
        self.discard_pile: List[int] = []
        self.discard_count: int = 0
        self.total_open_melds: int = 0
        self.flower_win_type: str | None = None
        self._flower_manager = FlowerManager(
            n_players=self.rules.n_players,
            enable_flower_wins=getattr(self.rules, "enable_flower_wins", True),
        )
        self.players: List[PlayerState] = [PlayerState(id=i) for i in range(self.rules.n_players)]
        self.n_gang: int = 0  # 場上槓數（供「一槓一」模式計算尾牌留置）
        self.reaction_queue: List[int] = []   # 要依序詢問反應的玩家（丟牌者之下一家開始）
        self.reaction_idx: int = 0
        self.claims: List[Dict[str, Any]] = []
        self.last_discard: Optional[Dict[str, Any]] = None
        self.done = False
        self.winner: Optional[int] = None
        self.win_source: Optional[str] = None
        self.win_tile: Optional[int] = None
        self.turn_at_win: Optional[int] = None
        self.win_by_gang_draw: bool = False      # 槓上自摸
        self.win_by_qiang_gang: bool = False     # 搶槓
        self._recent_gang_draw_pid: Optional[int] = None  # 剛補摸者
        self.qiang_gang_mode: bool = False       # 是否進入搶槓反應
        self.pending_kakan: Optional[Dict[str, Any]] = None  # {pid,tile}

    def _assign_seats_and_dealer(self) -> None:
        """Determine seat winds, seating order, and dealer selection for the round."""
        winds_cycle = ["E", "S", "W", "N"]
        preset_winds = getattr(self, "preset_seat_winds", None)
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
            order_map = {w: i for i, w in enumerate(winds_cycle)}
            pairs = [(order_map.get(w, 99), pid) for pid, w in enumerate(self.seat_winds)]
            pairs.sort()
            self.seating_order = [pid for _, pid in pairs if _ != 99]
        except Exception:
            self.seating_order = list(range(self.rules.n_players))
        self._seat_index = {pid: i for i, pid in enumerate(self.seating_order)}

        preset_dealer_pid = getattr(self, "preset_dealer_pid", None)
        if isinstance(preset_dealer_pid, int) and 0 <= preset_dealer_pid < self.rules.n_players:
            self.dealer_pid = int(preset_dealer_pid)
        else:
            self.dealer_pid = self.seating_order[0] if self.seating_order else 0

        self.quan_feng: str = (getattr(self, "preset_quan_feng", None) or getattr(self, "quan_feng", "E") or "E")
        ds = getattr(self, "preset_dealer_streak", None)
        self.dealer_streak = int(ds) if isinstance(ds, int) else 0
        self.winner_is_dealer: bool = False
        self.turn = self.dealer_pid
        self.phase = "TURN"  # or "REACTION"

    def _deal_initial_hands(self) -> None:
        """Distribute initial concealed tiles and draw the dealer's starting tile."""
        order_pids: List[int] = list(self.seating_order) if getattr(self, "seating_order", None) else list(range(self.rules.n_players))
        for _ in range(self.rules.initial_hand):
            for pid in order_pids:
                self._draw_into_hand(pid)
                if getattr(self, "done", False):
                    break
            if getattr(self, "done", False):
                break

        if not getattr(self, "done", False):
            self._draw_to_drawn(self.dealer_pid)

    def legal_actions(self, pid: Optional[int]=None) -> List[Action]:
        """List legal actions for current player (TURN) or current reactor (REACTION)."""
        if getattr(self, "done", False):
            return []
        if self.phase == "TURN":
            pid = self.turn if pid is None else pid
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
        else:  # REACTION
            if not self.reaction_queue or not (0 <= self.reaction_idx < len(self.reaction_queue)):
                return []
            pid = self.reaction_queue[self.reaction_idx]
            acts: List[Action] = [{"type": "PASS"}]
            discard = self.last_discard
            if discard is None:
                return acts
            tile = discard["tile"]
            player_state = self.players[pid]
            ting_locked = bool(getattr(player_state, "declared_ting", False))
            if self.qiang_gang_mode:
                if self.rules.allow_hu and is_win_16(player_state.hand + [tile], player_state.melds, self.rules):
                    acts.append({"type": "HU"})
                return acts
            if (
                (not ting_locked)
                and (self._seat_index.get(pid) == (self._seat_index.get(discard["pid"], -999) + 1) % self.rules.n_players)
                and self.rules.allow_chi
            ):
                for a, b in chi_options(tile, player_state.hand):
                    acts.append({"type": "CHI", "use": [a, b]})
            if (not ting_locked) and self.rules.allow_pong and player_state.hand.count(tile) >= 2:
                acts.append({"type": "PONG"})
            if (not ting_locked) and self.rules.allow_gang and player_state.hand.count(tile) >= 3:
                acts.append({"type": "GANG"})
            if self.rules.allow_hu and is_win_16(player_state.hand + [tile], player_state.melds, self.rules):
                acts.append({"type": "HU"})
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
            return self._handle_turn_action(action)
        return self._handle_reaction_action(action)

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

    def _handle_reaction_action(self, action: Action) -> Tuple[Observation, List[int], bool, Dict[str, Any]]:
        assert self.reaction_queue and 0 <= self.reaction_idx < len(self.reaction_queue), "reaction queue empty"
        pid = self.reaction_queue[self.reaction_idx]
        a_type = action.get("type")
        assert a_type in ("PASS", "CHI", "PONG", "GANG", "HU"), "反應期僅允許 PASS/CHI/PONG/GANG/HU"
        if self.players[pid].declared_ting and a_type not in ("PASS", "HU"):
            a_type = "PASS"
        if a_type != "PASS":
            claim = {"pid": pid, "type": a_type}
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
        self.reaction_idx += 1
        if self.reaction_idx < len(self.reaction_queue):
            next_pid = self.reaction_queue[self.reaction_idx]
            return self._obs(next_pid), [0] * self.rules.n_players, False, {}
        return self._resolve_reaction_window()

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
        self.phase = "REACTION"
        self.reaction_queue = [
            self.seating_order[(self._seat_index.get(pid, 0) + i) % self.rules.n_players]
            for i in (1, 2, 3)
        ]
        self.reaction_idx = 0
        self.claims = []
        next_pid = self.reaction_queue[self.reaction_idx]
        return self._obs(next_pid), [0] * self.rules.n_players, False, {}

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
        self.total_open_melds += 1
        self.players[claimer].drawn = None
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
        self.total_open_melds += 1
        self.players[claimer].drawn = None
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
    # ====== 內部輔助 ======
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

    def _handle_flower_draw(self, pid: int, tile: int) -> bool:
        """Delegate flower tracking to the manager and apply any outcome."""

        outcome = self._flower_manager.register_flower(
            pid=pid,
            tile=tile,
            players=self.players,
            round_done=getattr(self, "done", False),
        )
        return self._apply_flower_outcome(outcome)

    def _apply_flower_outcome(self, outcome: FlowerOutcome) -> bool:
        """Apply a flower outcome, finalizing wins when necessary."""

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
        """Backward-compatible wrapper delegating to the flower manager."""

        return self._handle_flower_draw(pid, tile)

    def _draw_into_hand(self, pid: int):
        """Draw from wall into hand, auto‑handling flowers (replacing immediately)."""
        while self._can_draw_from_wall():
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                if self._handle_flower_draw(pid, t):
                    return
                continue
            self.players[pid].hand.append(t)
            break

    def _draw_to_drawn(self, pid: int):
        """Draw from wall into the `drawn` slot, replacing flowers immediately."""
        self.players[pid].drawn = None
        while self._can_draw_from_wall():
            t = self.wall.pop()
            if is_flower(t) and self.rules.include_flowers:
                if self._handle_flower_draw(pid, t):
                    return
                continue
            self.players[pid].drawn = t
            break

    def _legal_discards(self, pid: int):
        """Return list of tile ids in hand that can be legally discarded (non‑flower)."""
        from .tiles import is_flower  # 重新導入以防循環
        return [t for t in self.players[pid].hand if not is_flower(t)]

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
            "hand": list(me.hand),
            "drawn": me.drawn,
            "flowers": list(me.flowers),
            "melds": [m if isinstance(m, dict) else list(m) for m in me.melds],
            "declared_ting": bool(getattr(me, "declared_ting", False)),
            # 公開資訊：所有玩家的副露與棄牌河
            "melds_all": [[m if isinstance(m, dict) else list(m) for m in p.melds] for p in self.players],
            "rivers": [list(p.river) for p in self.players],
            "live_public": self._public_live_counts(),
            "n_remaining": len(self.wall),
            "last_discard": dict(self.last_discard) if self.last_discard else None,
            "legal_actions": ([] if is_done else
                          self.legal_actions(pid=None if self.phase == "TURN" else pid)),
        }
        return obs

    def _public_live_counts(self) -> List[int]:
        """Return counts of live tiles after removing all publicly visible tiles."""

        counts = [4] * N_TILES
        for player in self.players:
            for tile in player.river:
                if tile is None:
                    continue
                value = int(tile)
                if 0 <= value < N_TILES and counts[value] > 0:
                    counts[value] -= 1
            for meld in player.melds:
                for value in _iter_public_meld_tiles(meld):
                    if counts[value] > 0:
                        counts[value] -= 1
        return counts
