"""Utility helpers for tile index pattern searches used by scoring rules."""

from __future__ import annotations

from functools import lru_cache


def _is_suited_idx(i: int) -> bool:
    """Return ``True`` if ``i`` represents a suited tile index (0-26 inclusive).

    Tile indices in ``core.tiles`` follow the standard Mahjong ordering where the
    first 27 indices correspond to the suited tiles (characters, dots, bamboos).
    """

    return 0 <= i <= 26


def _same_suit_triplet_ok(i: int) -> bool:
    """Return ``True`` if ``i``, ``i+1`` and ``i+2`` form a valid suited run."""

    if not (_is_suited_idx(i) and _is_suited_idx(i + 1) and _is_suited_idx(i + 2)):
        return False
    if i in (8, 17, 26):
        return False
    if (i // 9) != ((i + 1) // 9) or (i // 9) != ((i + 2) // 9):
        return False
    return True


@lru_cache(maxsize=None)
def _dfs_only_chows(state: tuple[int, ...], need: int, eye_used: bool) -> bool:
    """Return ``True`` if ``state`` can satisfy ``need`` chow melds and one eye.

    Args:
        state: A tuple of length 34 representing remaining tile counts. The tuple
            shape keeps the input hashable so the ``lru_cache`` can memoize
            intermediate states.
        need: Number of chow (sequence) melds still required.
        eye_used: ``True`` if an eye has already been allocated in the search.
    """

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
def _max_concealed_triplets(state: tuple[int, ...], need: int, eye_used: bool) -> int:
    """Return the max concealed triplets achievable from ``state``.

    Args:
        state: A tuple of length 34 representing remaining tile counts. The tuple
            form allows the ``lru_cache`` decorator to memoize intermediate
            search results.
        need: Number of melds still needed to complete the hand.
        eye_used: ``True`` if an eye has already been placed in the search.

    Returns:
        The maximum number of concealed triplets that can be formed while
        satisfying the ``need`` requirement. ``-1`` indicates no valid
        arrangement.
    """

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
