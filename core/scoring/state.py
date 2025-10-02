from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from ..hand import _counts34, waits_for_hand_16
from .common import is_honor
from .types import Meld, PlayerView, ScoringContext


@dataclass
class HandState:
    """Derived hand level information used by the scoring engine."""

    concealed_tiles: List[int]
    concealed_for_patterns: List[int]
    counts34: List[int]
    counts34_concealed: List[int]
    counts16: List[int]
    base_hand_for_waits: List[int]
    fixed_melds: int
    fixed_melds_pungs: int
    fixed_melds_chis: int
    need: int
    required_len: Optional[int]
    menqing: bool


@dataclass
class WinState:
    """Winning state abstraction (tsumo/ron tile related information)."""

    tsumo: bool
    win_source: str
    drawn: Optional[int]
    ron_tile: Optional[int]
    ron_tile_idx: Optional[int]
    win_tile_id: Optional[int]
    tenpai_before_draw: bool
    waits_for_du: List[int]
    waits_for_du_set: Set[int]


@dataclass
class DerivedScoringState:
    """Aggregated state shared across multiple scoring rules."""

    ctx: ScoringContext
    player: PlayerView
    melds: List[Meld]
    melds_dicts: List[Dict[str, Any]]
    flowers: List[int]
    has_flowers_total: bool
    flower_win_type: Optional[str]
    hand: HandState
    win: WinState
    all_tiles: List[int]
    has_honor_total: bool


def _normalize_win_source(source: Optional[str]) -> str:
    return str(source or "").upper()


def _ron_tile_from_context(ctx: ScoringContext, tsumo: bool) -> Optional[int]:
    if tsumo:
        return None
    wt = ctx.win_tile
    if isinstance(wt, int):
        return wt
    last_discard = ctx.last_discard
    if isinstance(last_discard, dict):
        tile = last_discard.get("tile")
        if isinstance(tile, int):
            return tile
    return None


def _build_meld_dicts(melds: Sequence[Meld]) -> List[Dict[str, Any]]:
    return [{"type": m.type, "tiles": list(m.tiles or [])} for m in melds]


def _derive_win_tile_id(tsumo: bool, drawn: Optional[int], ron_tile: Optional[int]) -> Optional[int]:
    if tsumo and isinstance(drawn, int):
        return drawn
    if (not tsumo) and isinstance(ron_tile, int):
        return ron_tile
    return None


def build_state(ctx: ScoringContext) -> DerivedScoringState:
    """Collect reusable state for ``score_with_breakdown`` rules."""

    winner = ctx.winner
    if winner is None:
        raise ValueError("build_state requires a winner in context")

    player = ctx.players[winner]
    melds = list(player.melds or [])
    melds_dicts = _build_meld_dicts(melds)

    flowers = list(player.flowers or [])
    has_flowers_total = any(
        isinstance(f, int) and _is_flower_tile(f) for f in flowers
    ) or bool(flowers)

    hand = list(player.hand or [])
    drawn = player.drawn
    win_source = _normalize_win_source(ctx.win_source)
    tsumo = win_source in ("TSUMO", "ZIMO")
    flower_win_type = getattr(ctx, "flower_win_type", None)

    concealed_tiles = list(hand)
    if tsumo and (drawn is not None):
        concealed_tiles.append(drawn)

    fixed_melds = sum(
        1
        for m in melds
        if (m.type or "").upper() in ("CHI", "PONG", "GANG", "ANGANG", "KAKAN")
    )
    need = 5 - fixed_melds
    required_len: Optional[int]
    if need >= 0:
        required_len = need * 3 + 2
    else:
        required_len = None

    ron_tile = _ron_tile_from_context(ctx, tsumo)

    concealed_for_patterns = list(concealed_tiles)
    if (not tsumo) and isinstance(ron_tile, int) and (required_len is not None):
        if len(concealed_for_patterns) == required_len - 1:
            concealed_for_patterns.append(ron_tile)

    menqing = all((m.type not in ("CHI", "PONG", "GANG", "KAKAN")) for m in melds)
    fixed_melds_pungs = 0
    fixed_melds_chis = 0
    for m in melds:
        mtype = (m.type or "").upper()
        if mtype in ("PONG", "GANG"):
            fixed_melds_pungs += 1
        elif mtype == "CHI":
            fixed_melds_chis += 1

    counts34 = _counts34(concealed_for_patterns)
    counts34_concealed = _counts34(concealed_tiles)
    ron_tile_idx = (
        ron_tile
        if (not tsumo) and isinstance(ron_tile, int) and 0 <= ron_tile < 34
        else None
    )

    win_tile_id = _derive_win_tile_id(tsumo, drawn, ron_tile)
    base_hand_for_waits = list(hand)
    if (
        isinstance(win_tile_id, int)
        and required_len is not None
        and len(base_hand_for_waits) == required_len
    ):
        try:
            base_hand_for_waits.remove(win_tile_id)
        except ValueError:
            pass
    counts16 = _counts34(base_hand_for_waits)

    tenpai_before_draw = False
    waits_for_du: List[int] = []
    if tsumo:
        try:
            tenpai_before_draw = bool(
                waits_for_hand_16(list(hand), melds_dicts, ctx.rules, exclude_exhausted=True)
            )
        except Exception:
            tenpai_before_draw = False
    try:
        waits_for_du = waits_for_hand_16(
            base_hand_for_waits,
            melds_dicts,
            ctx.rules,
            exclude_exhausted=False,
        )
    except Exception:
        waits_for_du = []
    waits_for_du_set = {w for w in waits_for_du if isinstance(w, int)}

    all_tiles: List[int] = list(concealed_for_patterns)
    for meld in melds:
        all_tiles.extend(meld.tiles or [])
    has_honor_total = any(_is_honor_tile(t) for t in all_tiles)

    hand_state = HandState(
        concealed_tiles=concealed_tiles,
        concealed_for_patterns=concealed_for_patterns,
        counts34=counts34,
        counts34_concealed=counts34_concealed,
        counts16=counts16,
        base_hand_for_waits=base_hand_for_waits,
        fixed_melds=fixed_melds,
        fixed_melds_pungs=fixed_melds_pungs,
        fixed_melds_chis=fixed_melds_chis,
        need=need,
        required_len=required_len,
        menqing=menqing,
    )

    win_state = WinState(
        tsumo=tsumo,
        win_source=win_source,
        drawn=drawn,
        ron_tile=ron_tile,
        ron_tile_idx=ron_tile_idx,
        win_tile_id=win_tile_id,
        tenpai_before_draw=tenpai_before_draw,
        waits_for_du=waits_for_du,
        waits_for_du_set=waits_for_du_set,
    )

    return DerivedScoringState(
        ctx=ctx,
        player=player,
        melds=melds,
        melds_dicts=melds_dicts,
        flowers=flowers,
        has_flowers_total=has_flowers_total,
        flower_win_type=flower_win_type,
        hand=hand_state,
        win=win_state,
        all_tiles=all_tiles,
        has_honor_total=has_honor_total,
    )


def _is_flower_tile(tile: int) -> bool:
    from ..tiles import is_flower

    try:
        return bool(is_flower(tile))
    except Exception:
        return False


def _is_honor_tile(tile: int) -> bool:
    return is_honor(tile)

