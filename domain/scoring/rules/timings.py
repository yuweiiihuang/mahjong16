from __future__ import annotations

from ..breakdown import ScoreAccumulator
from ..state import DerivedScoringState
from ..score_types import ScoringContext


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
    tsumo = win_src in ("TSUMO", "ZIMO")
    ron = win_src == "RON"
    # Before any open meld is claimed, the winner's discards are still in the river.
    first_go_around = open_melds == 0 and not player.river
    if tsumo and discards == 0:
        acc.add("tian_hu")
    elif first_go_around and (tsumo or (ron and discards == 1)):
        acc.add("di_hu")
    elif first_go_around and ron and discards > 1:
        acc.add("ren_hu")

    return True
