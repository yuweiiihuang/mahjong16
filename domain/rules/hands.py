from __future__ import annotations
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple

from ..tiles import is_flower


def _counts34(tiles: List[int]) -> List[int]:
    """Count occurrences of tile ids in the range [0, 33].

    Args:
      tiles: Tile ids. Any id outside 0..33 short‑circuits to an all‑zero list.

    Returns:
      A length‑34 list where index i is the count of tile id i.
    """
    c = [0] * 34
    for t in tiles:
        if 0 <= t < 34:
            c[t] += 1
        else:
            return [0] * 34
    return c


def is_suited_index(index: int) -> bool:
    """Return True if the tile index represents a suited tile (0-26 inclusive)."""

    return 0 <= index <= 26


def is_valid_chow_start(index: int) -> bool:
    """Return True if index, index+1 and index+2 form a valid suited chow."""

    if not (
        is_suited_index(index)
        and is_suited_index(index + 1)
        and is_suited_index(index + 2)
    ):
        return False
    if index in (8, 17, 26):
        return False
    if (index // 9) != ((index + 1) // 9) or (index // 9) != ((index + 2) // 9):
        return False
    return True


@lru_cache(maxsize=None)
def can_form_only_chows(state: Tuple[int, ...], need: int, eye_used: bool) -> bool:
    """Return True if chow-only melds plus an optional eye can satisfy the state."""

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

    if is_valid_chow_start(i):
        i1, i2 = i + 1, i + 2
        if state[i1] > 0 and state[i2] > 0:
            lst = list(state)
            lst[i] -= 1
            lst[i1] -= 1
            lst[i2] -= 1
            if can_form_only_chows(tuple(lst), need - 1, eye_used):
                return True

    if not eye_used and state[i] >= 2:
        lst = list(state)
        lst[i] -= 2
        if can_form_only_chows(tuple(lst), need, True):
            return True

    return False


@lru_cache(maxsize=None)
def max_concealed_triplets(state: Tuple[int, ...], need: int, eye_used: bool) -> int:
    """Return the maximum number of concealed triplets attainable for the state."""

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
        res = max_concealed_triplets(tuple(lst), need - 1, eye_used)
        if res >= 0:
            best = max(best, res + 1)

    if is_valid_chow_start(i):
        i1, i2 = i + 1, i + 2
        if state[i1] > 0 and state[i2] > 0:
            lst = list(state)
            lst[i] -= 1
            lst[i1] -= 1
            lst[i2] -= 1
            res = max_concealed_triplets(tuple(lst), need - 1, eye_used)
            if res >= 0:
                best = max(best, res)

    if not eye_used and state[i] >= 2:
        lst = list(state)
        lst[i] -= 2
        res = max_concealed_triplets(tuple(lst), need, True)
        if res >= 0:
            best = max(best, res)

    return best


def is_win_16(tiles: List[int], melds: List[Dict[str, Any]], rules) -> bool:
    """Check whether a 16+1 hand is a legal win (5 melds + 1 pair).

    Contract:
      Assumes Taiwan 16‑tile variant: a winning hand has 5 melds + 1 pair (17 tiles).
      Open `melds` are already completed; only their count reduces the needed concealed melds.

    Args:
      tiles: Concealed tiles to be evaluated (length must be `need*3 + 2`).
      melds: Open melds: dicts like {"type": "CHI"|"PONG"|"GANG", "tiles": [...]}.
      rules: Ruleset object; currently unused but reserved for future variants.

    Returns:
      True if the concealed tiles can be decomposed into the required melds and one pair.
    """
    fixed_melds = 0
    for m in melds or []:
        t = (m.get("type") or "").upper()
        # KONG 類（ANGANG/KAKAN/GANG）亦算一個面子
        if t in ("CHI", "PONG", "GANG", "ANGANG", "KAKAN"):
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

        if is_valid_chow_start(i):
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
    """List all waits (tile ids) that would win if drawn with the current 16.

    Args:
      hand16: Concealed tiles (exactly 16).
      melds: Open melds (env dicts: {"type", "tiles"}).
      rules: Ruleset passed to `is_win_16` for variant compatibility.
      exclude_exhausted: When True, exclude tiles already fully used by hand+melds (4 copies).

    Returns:
      Sorted list of tile ids 0..33 which make the hand win when added.
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
    """Compute waits after discarding from a 17‑tile state (hand + optional drawn).

    Simulates the post‑discard concealed 16, then delegates to `waits_for_hand_16`.

    Args:
      hand: Concealed tiles in hand (16 when ``drawn`` is set, else 17).
      drawn: The separate drawn tile, or None.
      melds: Open melds.
      discard_tile: The tile id to discard.
      discard_from: 'hand' to remove from hand (and add drawn back if any), or
        'drawn' to drop the drawn tile and keep hand untouched.
      rules: Ruleset.
      exclude_exhausted: Passed through to waits computation.

    Returns:
      List of tile ids that make a win after discarding ``discard_tile``.
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
