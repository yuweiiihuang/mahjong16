from __future__ import annotations

from typing import Dict, Sequence

from ..tiles import tile_to_str

HONOR_CHARS = ("E", "S", "W", "N", "C", "F", "P")
DRAGON_CHARS = ("C", "F", "P")

_LABEL_TO_ID: Dict[str, int] = {tile_to_str(i): i for i in range(34)}


def is_honor(tile: int) -> bool:
    """Return True if the tile represents a wind or dragon."""

    label = tile_to_str(tile)
    return bool(label) and label[0] in HONOR_CHARS


def is_dragon(tile: int) -> bool:
    """Return True if the tile represents a dragon (C/F/P)."""

    label = tile_to_str(tile)
    return bool(label) and label[0] in DRAGON_CHARS


def count_label(label: str, tiles: Sequence[int]) -> int:
    """Count the occurrences of a label within a tile collection."""

    tile_id = _LABEL_TO_ID.get(label)
    if tile_id is None:
        return 0
    return sum(1 for t in tiles if t == tile_id)


def tile_label(tile: int) -> str:
    """Return the textual label for a tile id."""

    return tile_to_str(tile)


