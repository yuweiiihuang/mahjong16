from __future__ import annotations

from functools import lru_cache
from typing import Dict, Sequence, Tuple

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


# === Wait / pattern helper routines ===

def _is_suited_idx(i: int) -> bool:
    return 0 <= i <= 26


def _same_suit_triplet_ok(i: int) -> bool:
    if not (_is_suited_idx(i) and _is_suited_idx(i + 1) and _is_suited_idx(i + 2)):
        return False
    if i in (8, 17, 26):
        return False
    if (i // 9) != ((i + 1) // 9) or (i // 9) != ((i + 2) // 9):
        return False
    return True


@lru_cache(maxsize=None)
def _dfs_only_chows(state: Tuple[int, ...], need: int, eye_used: bool) -> bool:
    if need == 0:
        total = sum(state)
        if eye_used:
            return total == 0
        if total != 2:
            return False
        return any(c == 2 for c in state)
    i = next((idx for idx, c in enumerate(state) if c > 0), -1)
    if i == -1:
        return False
    if _same_suit_triplet_ok(i):
        i1, i2 = i + 1, i + 2
        if state[i1] > 0 and state[i2] > 0:
            lst = list(state)
            lst[i] -= 1
            lst[i1] -= 1
            lst[i2] -= 1
            if _dfs_only_chows(tuple(lst), need - 1, eye_used):
                return True
    c = state[i]
    if not eye_used and c >= 2:
        lst = list(state)
        lst[i] -= 2
        if _dfs_only_chows(tuple(lst), need, True):
            return True
    return False


@lru_cache(maxsize=None)
def _max_concealed_triplets(state: Tuple[int, ...], need: int, eye_used: bool) -> int:
    if need < 0:
        return -1
    if need == 0:
        total = sum(state)
        if total == 0 and eye_used:
            return 0
        if not eye_used and total == 2 and any(c == 2 for c in state):
            return 0
        return -1

    i = next((idx for idx, c in enumerate(state) if c > 0), -1)
    if i == -1:
        return -1

    best = -1

    if state[i] >= 3:
        lst = list(state)
        lst[i] -= 3
        res = _max_concealed_triplets(tuple(lst), need - 1, eye_used)
        if res >= 0:
            best = max(best, res + 1)

    if _same_suit_triplet_ok(i):
        i1, i2 = i + 1, i + 2
        if state[i1] > 0 and state[i2] > 0:
            lst = list(state)
            lst[i] -= 1
            lst[i1] -= 1
            lst[i2] -= 1
            res = _max_concealed_triplets(tuple(lst), need - 1, eye_used)
            if res >= 0:
                best = max(best, res)

    if not eye_used and state[i] >= 2:
        lst = list(state)
        lst[i] -= 2
        res = _max_concealed_triplets(tuple(lst), need, True)
        if res >= 0:
            best = max(best, res)

    return best
