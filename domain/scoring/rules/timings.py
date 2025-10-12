from __future__ import annotations

from ..breakdown import ScoreAccumulator
from ..state import DerivedScoringState
from ..types import ScoringContext


def apply_timings_rules(
    ctx: ScoringContext, state: DerivedScoringState, acc: ScoreAccumulator
) -> bool:
    """Apply time-based bonuses such as 天聽、天胡."""

    player = state.player
    ting_declared_at = getattr(player, "ting_declared_at", None)
    ting_open_melds = getattr(player, "ting_declared_open_melds", None)
    if isinstance(ting_declared_at, int):
        if ting_declared_at <= 1:
            acc.add("tian_ting")
        elif ting_declared_at <= 8 and int(ting_open_melds or 0) == 0:
            acc.add("di_ting")

    win_src = state.win.win_source
    discards = max(0, int(getattr(ctx, "discard_count", 0) or 0))
    open_melds = max(0, int(getattr(ctx, "open_meld_count", 0) or 0))
    if win_src in ("TSUMO", "ZIMO") and discards == 0:
        acc.add("tian_hu")
    elif discards == 1 and win_src in ("RON", "TSUMO", "ZIMO"):
        acc.add("di_hu")
    elif discards > 1 and discards <= ctx.rules.n_players and open_melds == 0:
        acc.add("ren_hu")

    return True
