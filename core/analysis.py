"""Reusable analysis helpers for environment observations.

These helpers operate purely on observation data so they can be shared by UI,
bots, and analytics components without importing the console module.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from domain.gameplay.types import Observation


def simulate_after_discard(
    hand: Iterable[int],
    drawn: Optional[int],
    tile: int,
    source: str,
) -> List[int]:
    """Return the concealed hand after discarding ``tile`` from ``source``."""

    h = list(hand)
    if (source or "hand").lower() == "drawn":
        return h
    if tile in h:
        h.remove(tile)
    if drawn is not None:
        h.append(drawn)
    return h


def visible_count_global(tile_id: int, obs: Observation) -> int:
    """Count how many copies of ``tile_id`` are visible on the table."""

    cnt = sum(1 for t in (obs.get("hand") or []) if t == tile_id)
    for meld_list in (obs.get("melds_all") or []):
        for meld in (meld_list or []):
            for val in (meld.get("tiles") or []):
                if val == tile_id:
                    cnt += 1
    for river in (obs.get("rivers") or []):
        for val in river:
            if val == tile_id:
                cnt += 1
    return cnt


def visible_count_after(tile_id: int, hand_after: Iterable[int], obs: Observation) -> int:
    """Count visible tiles after discarding, using the provided hand snapshot."""

    cnt = sum(1 for t in hand_after if t == tile_id)
    for meld_list in (obs.get("melds_all") or []):
        for meld in (meld_list or []):
            for val in (meld.get("tiles") or []):
                if val == tile_id:
                    cnt += 1
    for river in (obs.get("rivers") or []):
        for val in river:
            if val == tile_id:
                cnt += 1
    return cnt
