from __future__ import annotations

from ..breakdown import ScoreAccumulator
from ..common import count_label
from ..state import DerivedScoringState
from ..types import ScoringContext


def apply_honors_rules(
    ctx: ScoringContext, state: DerivedScoringState, acc: ScoreAccumulator
) -> bool:
    """Apply dragon and wind related scoring patterns."""

    all_tiles = state.all_tiles
    cntC = count_label("C", all_tiles)
    cntF = count_label("F", all_tiles)
    cntP = count_label("P", all_tiles)

    tripC = cntC // 3
    tripF = cntF // 3
    tripP = cntP // 3
    pairC = cntC % 3 == 2
    pairF = cntF % 3 == 2
    pairP = cntP % 3 == 2

    triplets = tripC + tripF + tripP
    has_pair = pairC or pairF or pairP

    is_xiao_san_yuan = False
    is_da_san_yuan = False
    if triplets == 2 and has_pair:
        acc.add("xiao_san_yuan")
        is_xiao_san_yuan = True
    if triplets == 3:
        acc.add("da_san_yuan")
        is_da_san_yuan = True
    if triplets > 0 and not (is_xiao_san_yuan or is_da_san_yuan):
        acc.add("dragon_pung", count=triplets)

    cntE = count_label("E", all_tiles)
    cntS = count_label("S", all_tiles)
    cntW = count_label("W", all_tiles)
    cntN = count_label("N", all_tiles)

    trips = (cntE // 3) + (cntS // 3) + (cntW // 3) + (cntN // 3)
    pairs = ((cntE % 3) == 2) + ((cntS % 3) == 2) + ((cntW % 3) == 2) + (
        (cntN % 3) == 2
    )

    if trips == 3 and pairs == 1:
        acc.add("xiao_si_xi")
    is_da_si_xi = False
    if trips == 4:
        acc.add("da_si_xi")
        is_da_si_xi = True

    if not is_da_si_xi and getattr(ctx.rules, "enable_wind_flower_scoring", False):
        try:
            quan_feng = (getattr(ctx, "quan_feng", None) or "").upper()
            seat_winds = list(getattr(ctx, "seat_winds", []) or [])
            if 0 <= ctx.winner < len(seat_winds):
                my_wind = seat_winds[ctx.winner]
            else:
                my_wind = None
        except Exception:
            quan_feng, my_wind = None, None

        def _has_wind_triplet(label: str | None) -> bool:
            if not label:
                return False
            return count_label(label, all_tiles) // 3 >= 1

        if _has_wind_triplet(quan_feng):
            acc.add("quan_feng_ke")
        if _has_wind_triplet(my_wind):
            acc.add("men_feng_ke")

    return True
