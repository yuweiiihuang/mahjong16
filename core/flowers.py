from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from .state import PlayerState
from .tiles import N_FLOWERS, N_TILES, is_flower


@dataclass
class FlowerOutcome:
    """Result emitted after registering a flower draw."""

    round_ended: bool = False
    flower_type: Optional[str] = None
    winner_pid: Optional[int] = None
    loser_pid: Optional[int] = None
    win_tile: Optional[int] = None
    win_source: Optional[str] = None

    @property
    def is_win(self) -> bool:
        """Return True if the outcome represents a flower-triggered win."""

        return self.flower_type is not None


class FlowerManager:
    """Track flower collection state and detect flower-specific wins."""

    def __init__(self, n_players: int, enable_flower_wins: bool = True):
        self.n_players = n_players
        self.enable_flower_wins = enable_flower_wins
        self._player_sets: list[set[int]] = [set() for _ in range(n_players)]
        self._union: set[int] = set()

    def reset(self) -> None:
        """Clear all tracking for a new round."""

        self._player_sets = [set() for _ in range(self.n_players)]
        self._union = set()

    @property
    def player_sets(self) -> list[set[int]]:
        """Return per-player flower number collections."""

        return self._player_sets

    @property
    def union(self) -> set[int]:
        """Return the union of all flower numbers collected so far."""

        return self._union

    def register_flower(
        self,
        pid: int,
        tile: int,
        players: Sequence[PlayerState],
        round_done: bool = False,
    ) -> FlowerOutcome:
        """Record a newly drawn flower and return its impact on the round."""

        players[pid].flowers.append(tile)

        if round_done:
            return FlowerOutcome(round_ended=True)

        if not self.enable_flower_wins:
            return FlowerOutcome()

        flower_no = self._flower_no(tile)
        if flower_no is None:
            return FlowerOutcome()

        self._player_sets[pid].add(flower_no)
        self._union.add(flower_no)

        if len(self._union) < N_FLOWERS:
            return FlowerOutcome()

        ba_xian = self._check_ba_xian(pid, tile)
        if ba_xian is not None:
            return ba_xian

        qi_qiang = self._check_qi_qiang(players)
        if qi_qiang is not None:
            return qi_qiang

        return FlowerOutcome()

    def _check_ba_xian(self, pid: int, tile: int) -> FlowerOutcome | None:
        for candidate, fset in enumerate(self._player_sets):
            if len(fset) == N_FLOWERS:
                win_tile = tile if candidate == pid else None
                return FlowerOutcome(
                    round_ended=True,
                    flower_type="ba_xian",
                    winner_pid=candidate,
                    loser_pid=candidate,
                    win_tile=win_tile,
                    win_source="TSUMO",
                )
        return None

    def _check_qi_qiang(self, players: Sequence[PlayerState]) -> FlowerOutcome | None:
        for candidate, fset in enumerate(self._player_sets):
            if len(fset) == N_FLOWERS - 1:
                missing = list(self._union - fset)
                if not missing:
                    continue
                holder_pid, held_tile = self._find_flower_holder(players, missing[0])
                if holder_pid is None:
                    continue
                return FlowerOutcome(
                    round_ended=True,
                    flower_type="qi_qiang_yi",
                    winner_pid=candidate,
                    loser_pid=holder_pid,
                    win_tile=held_tile,
                    win_source="RON",
                )
        return None

    def _flower_no(self, tile: int) -> Optional[int]:
        if not is_flower(tile):
            return None
        return tile - N_TILES + 1

    def _find_flower_holder(
        self, players: Sequence[PlayerState], flower_no: int
    ) -> Tuple[Optional[int], Optional[int]]:
        for pid, player in enumerate(players):
            for t in getattr(player, "flowers", []):
                if self._flower_no(t) == flower_no:
                    return pid, t
        return None, None
