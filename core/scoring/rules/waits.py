from __future__ import annotations

from ..breakdown import ScoreAccumulator
from ..common import _dfs_only_chows
from ..state import DerivedScoringState
from ..types import ScoringContext


def _is_two_sided_ping_hu_wait(state: DerivedScoringState) -> bool:
    win_tile = state.win.win_tile_id
    waits_for_du_set = state.win.waits_for_du_set
    if not isinstance(win_tile, int):
        return False
    if win_tile < 0 or win_tile >= 34:
        return False
    if win_tile not in waits_for_du_set:
        return False
    if win_tile >= 27:
        return False

    counts16 = state.hand.counts16
    for a in range(33):
        b = a + 1
        if b >= 34:
            break
        if counts16[a] <= 0 or counts16[b] <= 0:
            continue
        if (a // 9) != (b // 9):
            continue
        left = a - 1 if (a % 9) != 0 else None
        right = b + 1 if (b % 9) != 8 else None
        if left is None or right is None:
            continue
        if (left // 9) != (a // 9) or (right // 9) != (a // 9):
            continue
        if win_tile == left and right in waits_for_du_set:
            return True
        if win_tile == right and left in waits_for_du_set:
            return True
    return False


def apply_waits_rules(
    ctx: ScoringContext, state: DerivedScoringState, acc: ScoreAccumulator
) -> bool:
    """Apply rules related to waits and tenpai states."""

    player = state.player
    if bool(getattr(player, "declared_ting", None)) or state.win.tenpai_before_draw:
        acc.add("ting")

    win_tile_id = state.win.win_tile_id
    waits_for_du_set = state.win.waits_for_du_set
    if isinstance(win_tile_id, int) and waits_for_du_set:
        if len(waits_for_du_set) == 1 and win_tile_id in waits_for_du_set:
            acc.add("du_ting")

    ping_hu_two_sided = _is_two_sided_ping_hu_wait(state)
    tsumo = state.win.tsumo
    hand = state.hand

    if (
        hand.fixed_melds_pungs == 0
        and hand.fixed_melds_chis > 0
        and hand.need >= 0
        and hand.required_len is not None
        and ping_hu_two_sided
        and not tsumo
    ):
        concealed_for_patterns = state.hand.concealed_for_patterns
        if len(concealed_for_patterns) == hand.required_len:
            if not state.has_flowers_total and not state.has_honor_total:
                counts34 = tuple(hand.counts34)
                if sum(hand.counts34) == len(concealed_for_patterns):
                    if _dfs_only_chows(counts34, hand.need, False):
                        acc.add("ping_hu")

    return True
