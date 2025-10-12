from __future__ import annotations

from ..breakdown import ScoreAccumulator
from ..state import DerivedScoringState
from ..score_types import ScoringContext


def _dead_wall_reserved(ctx: ScoringContext) -> int:
    mode = getattr(ctx.rules, "dead_wall_mode", "fixed")
    base = getattr(ctx.rules, "dead_wall_base", 16)
    if mode == "gang_plus_one":
        return base + int(getattr(ctx, "n_gang", 0) or 0)
    return base


def apply_base_rules(
    ctx: ScoringContext, state: DerivedScoringState, acc: ScoreAccumulator
) -> bool:
    """Apply menqing/tsumo/gang related base scoring rules."""

    table = ctx.table
    tsumo = state.win.tsumo
    menqing = state.hand.menqing

    if tsumo and getattr(ctx, "win_by_gang_draw", False):
        if menqing:
            acc.add("menqing")
    else:
        if menqing and tsumo and table.get("menqing_zimo", 3):
            acc.add("menqing_zimo")
        else:
            if menqing:
                acc.add("menqing")
            if tsumo:
                acc.add("zimo")

    if tsumo and ctx.wall_len == _dead_wall_reserved(ctx):
        acc.add("hai_di")
    if (not tsumo) and ctx.wall_len == _dead_wall_reserved(ctx):
        acc.add("he_di")

    if getattr(ctx, "win_by_gang_draw", False):
        acc.add("gang_shang")
    if getattr(ctx, "win_by_qiang_gang", False):
        acc.add("qiang_gang")

    if ctx.winner_is_dealer:
        try:
            n = int(getattr(ctx, "dealer_streak", 0) or 0)
        except Exception:
            n = 0
        acc.add("dealer", base=(2 * n + 1))

    return True
