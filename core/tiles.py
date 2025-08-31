"""Tile definitions and helpers for Mahjong16.

Defines numeric ids for tiles and flowers, conversions to string labels, and
utilities to generate a shuffled wall.
"""

from __future__ import annotations
from enum import IntEnum
import random
from typing import List

# 0..33: 34 tiles (萬/筒/條 1..9, 字 E/S/W/N/C/F/P)
# 34..41: 8 flowers (四季 + 四君子)
N_TILES = 34
N_FLOWERS = 8


class Tile(IntEnum):
    """Tile ids (0..33) as an IntEnum for readability in tests and code."""

    W1, W2, W3, W4, W5, W6, W7, W8, W9, \
    D1, D2, D3, D4, D5, D6, D7, D8, D9, \
    B1, B2, B3, B4, B5, B6, B7, B8, B9, \
    E, S, W, N, C, F, P = range(N_TILES)


def is_flower(x: int) -> bool:
    """Return True if id is a flower (>= N_TILES)."""
    return x >= N_TILES and x < N_TILES + N_FLOWERS


def flower_ids() -> List[int]:
    """Return the list of flower tile ids (length N_FLOWERS)."""
    return list(range(N_TILES, N_TILES + N_FLOWERS))


def full_wall(include_flowers: bool = True, rng: random.Random | None = None) -> List[int]:
    """Build a shuffled wall of tiles (4 copies of each, plus optional flowers).

    Args:
      include_flowers: Whether to include flowers in the wall.
      rng: Optional random.Random to use.

    Returns:
      Shuffled list of tile ids representing the wall.
    """
    r = rng if rng else random
    wall: List[int] = []
    for t in range(N_TILES):
        wall += [t] * 4
    if include_flowers:
        wall += flower_ids()  # 四季四君子各1
    r.shuffle(wall)
    return wall


def tile_to_str(t: int) -> str:
    """Convert a tile id to a short label (e.g., '1W', 'E', 'F')."""
    if is_flower(t):
        return f"F{t - N_TILES + 1}"
    names = [
        *[f"{i+1}W" for i in range(9)],
        *[f"{i+1}D" for i in range(9)],
        *[f"{i+1}B" for i in range(9)],
        "E", "S", "W", "N", "C", "F", "P",
    ]
    return names[int(t)]


def hand_to_str(hand: List[int]) -> str:
    """Convert a sequence of tiles into a space-separated, sorted label string."""
    return " ".join(sorted([tile_to_str(t) for t in hand]))
