from __future__ import annotations

from domain.rules.hands import can_form_only_chows
from ..breakdown import ScoreAccumulator
from ..state import DerivedScoringState
from ..score_types import ScoringContext


def _is_two_sided_ping_hu_wait(state: DerivedScoringState) -> bool:
    win_tile = state.win.win_tile_id
    waits_for_du_set = state.win.waits_for_du_set
    if not isinstance(win_tile, int) or not 0 <= win_tile < 27 or win_tile not in waits_for_du_set:
        return False

    hand = state.hand
    for step in (1, -1):
        first, second = win_tile + step, win_tile + 2 * step
        opposite = win_tile + 3 * step
        if opposite // 9 != win_tile // 9 or opposite not in waits_for_du_set:
            continue
        if hand.counts16[first] == 0 or hand.counts16[second] == 0:
            continue
        # The same remainder must supply every other chow and the pair for either end.
        remainder = list(hand.counts16)
        remainder[first] -= 1
        remainder[second] -= 1
        if can_form_only_chows(tuple(remainder), hand.need - 1, False):
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

    hand = state.hand
    if (
        hand.fixed_melds_pungs == 0
        and hand.need > 0
        and len(hand.concealed_for_patterns) == hand.required_len
        and not state.has_flowers_total
        and not state.has_honor_total
        and not state.win.tsumo
        and _is_two_sided_ping_hu_wait(state)
    ):
        acc.add("ping_hu")

    return True
