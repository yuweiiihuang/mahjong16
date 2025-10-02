from __future__ import annotations

from typing import Dict

from ..breakdown import ScoreAccumulator
from ..common import _max_concealed_triplets, is_honor, tile_label
from ..state import DerivedScoringState
from ..types import ScoringContext


def _collect_suits(all_tiles: list[int]) -> set[str]:
    suits: set[str] = set()
    for tile in all_tiles:
        label = tile_label(tile)
        if len(label) == 2:
            suits.add(label[1])
    return suits


def apply_patterns_rules(
    ctx: ScoringContext, state: DerivedScoringState, acc: ScoreAccumulator
) -> bool:
    """Apply color and pattern-based scoring rules."""

    all_tiles = state.all_tiles
    if all_tiles:
        if all(is_honor(t) for t in all_tiles):
            acc.add("zi_yi_se")
        else:
            suits = _collect_suits(all_tiles)
            if len(suits) == 1:
                if state.has_honor_total:
                    acc.add("hun_yi_se")
                else:
                    acc.add("qing_yi_se")

    hand = state.hand
    concealed_for_patterns = hand.concealed_for_patterns
    if hand.fixed_melds_chis == 0 and hand.need >= 0 and hand.required_len is not None:
        if len(concealed_for_patterns) == hand.required_len:
            counts: Dict[str, int] = {}
            for tile in concealed_for_patterns:
                label = tile_label(tile)
                counts[label] = counts.get(label, 0) + 1
            mods = [c % 3 for c in counts.values()]
            if mods.count(2) == 1 and all(m in (0, 2) for m in mods):
                acc.add("peng_peng_hu")

    concealed_triplets = 0
    if hand.need >= 0 and hand.required_len is not None:
        if len(concealed_for_patterns) == hand.required_len:
            max_triplets = _max_concealed_triplets(
                tuple(hand.counts34), hand.need, False
            )
            ron_tile_idx = state.win.ron_tile_idx
            counts34 = hand.counts34
            counts34_concealed = hand.counts34_concealed
            if ron_tile_idx is not None and max_triplets > 0:
                if (
                    counts34[ron_tile_idx] >= 3
                    and counts34_concealed[ron_tile_idx] < 3
                    and counts34[ron_tile_idx]
                    == counts34_concealed[ron_tile_idx] + 1
                ):
                    max_triplets = max(max_triplets - 1, 0)
            if max_triplets > 0:
                concealed_triplets += max_triplets
            elif max_triplets == 0:
                concealed_triplets += 0
    concealed_triplets += sum(
        1 for m in state.melds if (m.type or "").upper() == "ANGANG"
    )
    if concealed_triplets >= 5:
        acc.add("wu_an_ke")
    elif concealed_triplets >= 4:
        acc.add("si_an_ke")
    elif concealed_triplets >= 3:
        acc.add("san_an_ke")

    if not state.win.tsumo:
        open_from_others = [
            m
            for m in state.melds
            if (m.type or "").upper() in ("CHI", "PONG", "GANG", "KAKAN")
            and m.from_pid is not None
        ]
        concealed_melds = [
            m for m in state.melds if (m.type or "").upper() == "ANGANG"
        ]
        if (
            len(open_from_others) >= 5
            and not concealed_melds
            and len(state.hand.concealed_tiles) <= 1
        ):
            acc.add("quan_qiu_ren")

    return True
