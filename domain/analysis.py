"""Reusable analysis helpers for environment observations.

These helpers operate purely on observation data so they can be shared by UI,
bots, and analytics components without importing console widgets.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from domain.gameplay.game_types import Observation


def simulate_after_discard(
    hand: Iterable[int],
    drawn: Optional[int],
    tile: int,
    source: str,
) -> List[int]:
    """Return the concealed hand after discarding ``tile`` from ``source``."""

    updated_hand = list(hand)
    if (source or "").lower() == "drawn":
        return updated_hand
    if tile in updated_hand:
        updated_hand.remove(tile)
    if drawn is not None:
        updated_hand.append(drawn)
    return updated_hand


def _count_in_melds_and_rivers(tile_id: int, obs: Observation) -> int:
    """Helper to count tile occurrences in melds and rivers."""
    count = 0
    for meld_list in (obs.get("melds_all") or []):
        for meld in (meld_list or []):
            for value in (meld.get("tiles") or []):
                if value == tile_id:
                    count += 1
    for river in (obs.get("rivers") or []):
        for value in river:
            if value == tile_id:
                count += 1
    return count


def visible_count_global(tile_id: int, obs: Observation) -> int:
    """Count how many copies of ``tile_id`` are visible on the table."""

    count = sum(1 for t in (obs.get("hand") or []) if t == tile_id)
    count += _count_in_melds_and_rivers(tile_id, obs)
    return count


def visible_count_after(tile_id: int, hand_after: Iterable[int], obs: Observation) -> int:
    """Count visible tiles after discarding, using the provided hand snapshot."""

    count = sum(1 for t in hand_after if t == tile_id)
    count += _count_in_melds_and_rivers(tile_id, obs)
    return count
