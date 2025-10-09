from __future__ import annotations
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .tiles import is_flower


def _counts34(tiles: List[int]) -> Tuple[int, ...]:
    """Return a canonical count tuple for tiles in the range [0, 33]."""

    counts = [0] * 34
    for tile in tiles:
        if 0 <= tile < 34:
            counts[tile] += 1
        else:
            return tuple([0] * 34)
    return tuple(counts)


def _is_suited(idx: int) -> bool:
    return 0 <= idx <= 26


def _same_suit_triplet_ok(idx: int) -> bool:
    if not (_is_suited(idx) and _is_suited(idx + 1) and _is_suited(idx + 2)):
        return False
    if idx in (8, 17, 26):
        return False
    suit = idx // 9
    return suit == ((idx + 1) // 9) == ((idx + 2) // 9)


# Cache size is bounded to avoid unbounded growth during long-lived processes.
_MELD_CACHE_MAXSIZE = 100_000


@lru_cache(maxsize=_MELD_CACHE_MAXSIZE)
def _dfs_melds(state: Tuple[int, ...], need: int, eye_used: bool) -> bool:
    """Depth-first search for meld decomposition with memoisation."""

    if need == 0:
        total = sum(state)
        if eye_used:
            return total == 0
        if total != 2:
            return False
        return any(count == 2 for count in state)

    first = next((idx for idx, count in enumerate(state) if count > 0), -1)
    if first == -1:
        return False

    count_first = state[first]
    if count_first >= 3:
        lst = list(state)
        lst[first] -= 3
        if _dfs_melds(tuple(lst), need - 1, eye_used):
            return True

    if _same_suit_triplet_ok(first):
        i1, i2 = first + 1, first + 2
        if state[i1] > 0 and state[i2] > 0:
            lst = list(state)
            lst[first] -= 1
            lst[i1] -= 1
            lst[i2] -= 1
            if _dfs_melds(tuple(lst), need - 1, eye_used):
                return True

    if not eye_used and count_first >= 2:
        lst = list(state)
        lst[first] -= 2
        if _dfs_melds(tuple(lst), need, True):
            return True

    return False


def clear_meld_cache() -> None:
    """Clear cached meld search states."""

    _dfs_melds.cache_clear()


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

    counts = _counts34(tiles)
    return _dfs_melds(counts, need_melds, False)


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
