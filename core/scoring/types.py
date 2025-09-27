from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..ruleset import Ruleset


@dataclass
class ScoringTable:
    """In‑memory scoring table for one profile with label lookup.

    Attributes:
      values: Mapping from scoring key (e.g., 'zimo', 'menqing') to base points (台數).
      labels: Mapping from key to human‑readable label.
    """

    values: Dict[str, int]
    labels: Dict[str, str]

    def get(self, key: str, default: int = 0) -> int:
        """Fetch integer value for a scoring key with a default fallback.

        Args:
          key: Scoring item key.
          default: Fallback value when key is missing or invalid.

        Returns:
          Integer value for the key or the default.
        """
        v = self.values.get(key, default)
        try:
            return int(v)
        except Exception:
            return default


@dataclass
class Meld:
    """Typed meld view used by the scoring context.

    Attributes:
      type: 'CHI' | 'PONG' | 'GANG' (uppercase expected by engine).
      tiles: Constituent tile ids (3 for PONG, 3 for CHI, 4 for GANG).
      from_pid: Optional discarder id for open melds, if available.
    """

    type: str
    tiles: List[int]
    from_pid: Optional[int] = None


@dataclass
class PlayerView:
    """Read‑only snapshot of player state for scoring.

    Only fields relevant for the scoring engine are included.
    """

    id: int
    hand: List[int]
    drawn: Optional[int]
    melds: List[Meld]
    flowers: List[int]
    river: List[int]
    declared_ting: bool


@dataclass
class ScoringContext:
    """Typed snapshot of everything the scoring engine needs.

    Attributes:
      rules: Active Ruleset (for reserved tail, players, etc.).
      players: Typed per‑player views.
      winner: Index of winner (or None when no winner).
      win_source: 'TSUMO' | 'RON' | None.
      win_tile: Id of the winning tile if known.
      last_discard: Original last discard dict (for ron inference).
      turn_at_win: Active player id when win occurred (discarder for RON).
      wall_len: Remaining wall size.
      n_gang: Number of ganged melds on table (affects reserved tail in gang_plus_one).
      table: ScoringTable for this profile.
      winner_is_dealer: Optional flag for dealer bonus.
      win_by_gang_draw: Optional flag for '槓上' types.
    """

    rules: Ruleset
    players: List[PlayerView]
    winner: Optional[int]
    win_source: Optional[str]
    win_tile: Optional[int]
    last_discard: Optional[Dict[str, Any]]
    turn_at_win: Optional[int]
    wall_len: int
    n_gang: int
    table: ScoringTable
    winner_is_dealer: bool = False
    win_by_gang_draw: bool = False
    win_by_qiang_gang: bool = False
    # 新增：圈風、門風、莊家資訊（供風牌/莊家台計算）
    quan_feng: str | None = None         # 'E' | 'S' | 'W' | 'N'
    seat_winds: list[str] | None = None  # 索引為 pid，值為 'E'/'S'/'W'/'N'
    dealer_pid: int | None = None
    dealer_streak: int = 0

    @staticmethod
    def from_env(env, table: ScoringTable) -> "ScoringContext":
        """Build ScoringContext from an env snapshot and a preloaded table.

        Args:
          env: Mahjong16Env instance at end of round.
          table: ScoringTable for the active scoring profile.

        Returns:
          A populated ScoringContext ready for scoring.
        """
        players = []
        for p in env.players:
            meld_objs: List[Meld] = []
            for m in (p.get("melds") or []):
                if isinstance(m, dict):
                    meld_objs.append(Meld(type=str(m.get("type", "")).upper(), tiles=list(m.get("tiles") or []), from_pid=m.get("from_pid")))
                else:
                    try:
                        # fallback if tuple/list
                        mt = str(m[0]).upper() if m else ""
                        meld_objs.append(Meld(type=mt, tiles=list(m[1] or [])))
                    except Exception:
                        meld_objs.append(Meld(type="", tiles=[]))
            players.append(
                PlayerView(
                    id=p.get("id"),
                    hand=list(p.get("hand") or []),
                    drawn=p.get("drawn"),
                    melds=meld_objs,
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
            turn_at_win=getattr(env, "turn_at_win", None),
            wall_len=len(getattr(env, "wall", []) or []),
            n_gang=getattr(env, "n_gang", 0),
            table=table,
            winner_is_dealer=bool(getattr(env, "winner_is_dealer", False)),
            win_by_gang_draw=bool(getattr(env, "win_by_gang_draw", False)),
            win_by_qiang_gang=bool(getattr(env, "win_by_qiang_gang", False)),
            quan_feng=getattr(env, "quan_feng", None),
            seat_winds=getattr(env, "seat_winds", None),
            dealer_pid=getattr(env, "dealer_pid", None),
            dealer_streak=int(getattr(env, "dealer_streak", 0) or 0),
        )
