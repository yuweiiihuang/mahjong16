from __future__ import annotations
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple

from .tiles import is_flower


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
