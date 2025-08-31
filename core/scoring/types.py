from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..ruleset import Ruleset


@dataclass
class ScoringTable:
    values: Dict[str, int]
    labels: Dict[str, str]

    def get(self, key: str, default: int = 0) -> int:
        v = self.values.get(key, default)
        try:
            return int(v)
        except Exception:
            return default


@dataclass
class PlayerView:
    id: int
    hand: List[int]
    drawn: Optional[int]
    melds: List[Dict[str, Any]]
    flowers: List[int]
    river: List[int]
    declared_ting: bool


@dataclass
class ScoringContext:
    rules: Ruleset
    players: List[PlayerView]
    winner: Optional[int]
    win_source: Optional[str]
    win_tile: Optional[int]
    last_discard: Optional[Dict[str, Any]]
    wall_len: int
    n_gang: int
    table: ScoringTable
    winner_is_dealer: bool = False
    win_by_gang_draw: bool = False

    @staticmethod
    def from_env(env, table: ScoringTable) -> "ScoringContext":
        players = []
        for p in env.players:
            players.append(
                PlayerView(
                    id=p.get("id"),
                    hand=list(p.get("hand") or []),
                    drawn=p.get("drawn"),
                    melds=list(p.get("melds") or []),
                    flowers=list(p.get("flowers") or []),
                    river=list(p.get("river") or []),
                    declared_ting=bool(p.get("declared_ting", False)),
                )
            )
        return ScoringContext(
            rules=env.rules,
            players=players,
            winner=getattr(env, "winner", None),
            win_source=getattr(env, "win_source", None),
            win_tile=getattr(env, "win_tile", None),
            last_discard=getattr(env, "last_discard", None),
            wall_len=len(getattr(env, "wall", []) or []),
            n_gang=getattr(env, "n_gang", 0),
            table=table,
            winner_is_dealer=bool(getattr(env, "winner_is_dealer", False)),
            win_by_gang_draw=bool(getattr(env, "win_by_gang_draw", False)),
        )

