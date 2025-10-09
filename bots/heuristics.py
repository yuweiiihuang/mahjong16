"""Reusable heuristic helpers for Mahjong16 bots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, MutableSequence, Optional, Sequence, Tuple

Tile = int


@dataclass(frozen=True)
class HeuristicSnapshot:
    """Summary of the heuristic evaluation for a hand state."""

    cost: int
    melds: int
    has_pair: bool
    singles: int


Counts34 = List[int]


def counts34(tiles: Iterable[Tile]) -> Counts34:
    """Map tiles into the standard 34-tile histogram."""

    histogram = [0] * 34
    for tile in tiles:
        if 0 <= tile < 34:
            histogram[tile] += 1
    return histogram


def _remove_triplets(counts: MutableSequence[int]) -> int:
    """Greedily consume triplets (刻) from the histogram."""

    melds = 0
    for idx, value in enumerate(counts):
        if value >= 3:
            triplets = value // 3
            counts[idx] -= 3 * triplets
            melds += triplets
    return melds


def _remove_sequences(counts: MutableSequence[int], suit_start: int) -> int:
    """Greedily consume sequences (順) within a single suit."""

    melds = 0
    end = suit_start + 9
    while True:
        made = 0
        for idx in range(suit_start, end - 2):
            take = min(counts[idx], counts[idx + 1], counts[idx + 2])
            if take:
                counts[idx] -= take
                counts[idx + 1] -= take
                counts[idx + 2] -= take
                melds += take
                made += take
        if made == 0:
            break
    return melds


def estimate_melds_and_pair(counts: Sequence[int]) -> Tuple[int, bool, int]:
    """Estimate meld count, whether a pair exists, and the singles penalty."""

    singles = sum(1 for value in counts if value == 1)
    mutable = list(counts)
    melds = _remove_triplets(mutable)
    melds += _remove_sequences(mutable, 0)
    melds += _remove_sequences(mutable, 9)
    melds += _remove_sequences(mutable, 18)

    has_pair = any(value >= 2 for value in mutable)
    return melds, has_pair, singles


def count_fixed_melds(melds: Optional[Sequence[dict]]) -> int:
    """Number of exposed melds present in the observation."""

    if not melds:
        return 0
    exposed = {"CHI", "PONG", "GANG"}
    return sum(1 for meld in melds if (meld.get("type") or "").upper() in exposed)


def heuristic(hand: Sequence[Tile], melds: Optional[Sequence[dict]]) -> HeuristicSnapshot:
    """Compute heuristic metrics for the current hand state."""

    fixed_melds = count_fixed_melds(melds)
    need = max(0, 5 - fixed_melds)
    histogram = counts34(hand)
    melds_from_hand, has_pair, singles = estimate_melds_and_pair(histogram)

    missing_melds = max(0, need - melds_from_hand)
    missing_eye = 0 if has_pair else 1
    cost = missing_melds * 10 + missing_eye * 3 + min(3, singles)
    return HeuristicSnapshot(cost, melds_from_hand, has_pair, singles)


__all__ = [
    "Counts34",
    "HeuristicSnapshot",
    "Tile",
    "count_fixed_melds",
    "counts34",
    "estimate_melds_and_pair",
    "heuristic",
]
