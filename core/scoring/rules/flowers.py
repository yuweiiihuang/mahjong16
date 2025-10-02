from __future__ import annotations

from ..breakdown import ScoreAccumulator
from ..state import DerivedScoringState
from ..types import ScoringContext


def _flower_no(tile: int) -> int | None:
    from ...tiles import tile_to_str

    label = tile_to_str(tile)
    if label and label.startswith("F"):
        try:
            return int(label[1:])
        except Exception:
            return None
    return None


def apply_flowers_rules(
    ctx: ScoringContext, state: DerivedScoringState, acc: ScoreAccumulator
) -> bool:
    """Apply flower related scoring, handling early flower wins."""

    flower_win_type = state.flower_win_type
    if flower_win_type:
        if flower_win_type == "ba_xian":
            acc.add("ba_xian")
        elif flower_win_type == "qi_qiang_yi":
            acc.add("qi_qiang_yi")
        else:
            acc.add(str(flower_win_type))
        return False

    flowers = state.flowers
    if not flowers or not getattr(ctx.rules, "enable_wind_flower_scoring", False):
        return True

    fnums = sorted(
        n for n in (_flower_no(tile) for tile in flowers) if isinstance(n, int)
    )
    fset = set(fnums)

    zheng_map = {
        "E": {1, 5},
        "S": {2, 6},
        "W": {3, 7},
        "N": {4, 8},
    }

    try:
        seat_winds = list(getattr(ctx, "seat_winds", []) or [])
        if 0 <= ctx.winner < len(seat_winds):
            my_wind = seat_winds[ctx.winner]
        else:
            my_wind = None
    except Exception:
        my_wind = None
    if isinstance(my_wind, str):
        targets = zheng_map.get(my_wind.upper(), set())
        cnt_zheng = len(fset.intersection(targets))
        if cnt_zheng > 0:
            acc.add("zheng_hua", count=cnt_zheng)

    has_seasons = {1, 2, 3, 4}.issubset(fset)
    has_gentlemen = {5, 6, 7, 8}.issubset(fset)
    hua_gang_cnt = int(has_seasons) + int(has_gentlemen)
    if hua_gang_cnt:
        acc.add("hua_gang", count=hua_gang_cnt)

    unique_flowers = len(fset)
    if unique_flowers == 8:
        acc.add("ba_xian")
    elif unique_flowers == 7:
        acc.add("qi_qiang_yi")

    return True
