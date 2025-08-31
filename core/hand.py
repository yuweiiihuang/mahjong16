from __future__ import annotations
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple

from .tiles import is_flower


def _counts34(tiles: List[int]) -> List[int]:
    c = [0] * 34
    for t in tiles:
        if 0 <= t < 34:
            c[t] += 1
        else:
            return [0] * 34
    return c


def is_win_16(tiles: List[int], melds: List[Dict[str, Any]], rules) -> bool:
    """Return True if 16+1 tiles can form 5 melds + 1 pair, given existing melds.

    This mirrors the prior implementation in core.judge and is kept pure
    (no IO, no env access) so it is easy to unit test.
    """
    fixed_melds = 0
    for m in melds or []:
        t = (m.get("type") or "").upper()
        if t in ("CHI", "PONG", "GANG"):
            fixed_melds += 1
    need_melds = 5 - fixed_melds
    if need_melds < 0:
        return False
    if len(tiles) != need_melds * 3 + 2:
        return False

    counts = [0] * 34
    for t in tiles:
        if 0 <= t < 34:
            counts[t] += 1
        else:
            return False

    def is_suited(i: int) -> bool:
        return 0 <= i <= 26

    def same_suit_triplet_ok(i: int) -> bool:
        if not (is_suited(i) and is_suited(i + 1) and is_suited(i + 2)):
            return False
        if i in (8, 17, 26):
            return False
        if (i // 9) != ((i + 1) // 9) or (i // 9) != ((i + 2) // 9):
            return False
        return True

    @lru_cache(maxsize=None)
    def dfs(state: tuple, need: int, eye_used: bool) -> bool:
        if need == 0:
            total = sum(state)
            if eye_used:
                return total == 0
            if total != 2:
                return False
            for c in state:
                if c == 2:
                    return True
            return False

        i = next((idx for idx, c in enumerate(state) if c > 0), -1)
        if i == -1:
            return False

        if state[i] >= 3:
            lst = list(state)
            lst[i] -= 3
            if dfs(tuple(lst), need - 1, eye_used):
                return True

        if same_suit_triplet_ok(i):
            i1, i2 = i + 1, i + 2
            if state[i1] > 0 and state[i2] > 0:
                lst = list(state)
                lst[i] -= 1
                lst[i1] -= 1
                lst[i2] -= 1
                if dfs(tuple(lst), need - 1, eye_used):
                    return True

        if not eye_used and state[i] >= 2:
            lst = list(state)
            lst[i] -= 2
            if dfs(tuple(lst), need, True):
                return True

        return False

    return dfs(tuple(counts), need_melds, False)


def waits_for_hand_16(
    hand16: List[int],
    melds: List[Dict[str, Any]],
    rules,
    *,
    exclude_exhausted: bool = True,
) -> List[int]:
    """
    Given 16 tiles and open melds, return all tiles that complete a win on draw.
    Excludes tiles already exhausted in hand+melds when exclude_exhausted=True.
    """
    waits: List[int] = []
    used_counts = [0] * 34
    for t in hand16:
        if 0 <= t < 34:
            used_counts[t] += 1
    for m in (melds or []):
        for t in (m.get("tiles") or []):
            if 0 <= t < 34:
                used_counts[t] += 1

    for t in range(34):
        if is_flower(t):
            continue
        if exclude_exhausted and used_counts[t] >= 4:
            continue
        if is_win_16(hand16 + [t], melds, rules):
            waits.append(t)
    return waits


def waits_after_discard_17(
    hand: List[int],
    drawn: Optional[int],
    melds: List[Dict[str, Any]],
    discard_tile: int,
    discard_from: str,
    rules,
    *,
    exclude_exhausted: bool = True,
) -> List[int]:
    """
    Simulate discarding a tile from hand/drawn, return waits for the resulting 16.
    """
    h = list(hand)
    if (discard_from or "hand").lower() == "drawn":
        pass
    else:
        if discard_tile in h:
            h.remove(discard_tile)
        if drawn is not None:
            h.append(drawn)
    return waits_for_hand_16(h, melds, rules, exclude_exhausted=exclude_exhausted)

