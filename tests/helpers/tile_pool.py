"""Utilities to allocate Mahjong tiles in tests without violating copy limits."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, List

from sdk import N_TILES, Tile, flower_ids


class TilePool:
    """Simple multiset tracker for Mahjong tiles.

    Tests can draw explicit tiles for hands, melds, or walls while ensuring no
    tile id is used more than the four copies available in a standard set (plus
    optional single-copy flowers).
    """

    def __init__(self, include_flowers: bool = False) -> None:
        self.include_flowers = include_flowers
        self._counts: Counter[int] = Counter({tid: 4 for tid in range(N_TILES)})
        if include_flowers:
            for fid in flower_ids():
                self._counts[fid] = 1

    def take(self, tiles: Iterable[int | Tile]) -> List[int]:
        """Remove the requested tiles from the pool and return them as ints."""
        drawn = [int(t) for t in tiles]
        for tid in drawn:
            if self._counts[tid] <= 0:
                raise ValueError(f"tile {tid} exhausted while allocating test setup")
        for tid in drawn:
            self._counts[tid] -= 1
        return drawn

    def remaining(self) -> List[int]:
        """Return the remaining tiles in deterministic order for wall setup."""
        wall: List[int] = []
        for tid in range(N_TILES):
            count = self._counts[tid]
            if count > 0:
                wall.extend([tid] * count)
        if self.include_flowers:
            for fid in flower_ids():
                count = self._counts[fid]
                if count > 0:
                    wall.extend([fid] * count)
        return wall


def move_tile_to_tail(wall: List[int], tile: int | Tile) -> None:
    """Move the given tile to the end of the wall (drawn next)."""
    tid = int(tile)
    if not wall:
        raise ValueError("cannot move tile in an empty wall")
    try:
        idx = wall.index(tid)
    except ValueError as exc:  # pragma: no cover - guard against test setup errors where requested tile is not in wall
        raise ValueError(f"tile {tid} not present in wall") from exc
    wall[idx], wall[-1] = wall[-1], wall[idx]
