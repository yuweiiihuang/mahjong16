"""Greedy bot for smoke tests.

The strategy is intentionally light-weight: it evaluates candidate actions with a
hand-shape heuristic that approximates how many melds and pairs can be formed.
The bot is not meant to be strong, but it provides deterministic behaviour that
is useful for unit tests and manual debugging.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, MutableSequence, Optional, Sequence, Tuple

from core.tiles import tile_to_str


# ---------------------------------------------------------------------------
# Typed helpers


Tile = int


@dataclass(frozen=True)
class HeuristicSnapshot:
    """Summary of the heuristic evaluation for a hand state."""

    cost: int
    melds: int
    has_pair: bool
    singles: int


def _counts34(tiles: Iterable[Tile]) -> List[int]:
    """Map tiles into the standard 34-tile histogram."""

    counts = [0] * 34
    for tile in tiles:
        if 0 <= tile < 34:
            counts[tile] += 1
    return counts


def _remove_triplets(counts: MutableSequence[int]) -> int:
    """Greedily consume triplets (刻) from the histogram."""

    melds = 0
    for idx, value in enumerate(counts):
        if value >= 3:
            triplets = value // 3
            counts[idx] -= 3 * triplets
            melds += triplets
    return melds


def _remove_sequences(counts: MutableSequence[int], suit_start: int) -> int:
    """Greedily consume sequences (順) within a single suit."""

    melds = 0
    end = suit_start + 9
    while True:
        made = 0
        for idx in range(suit_start, end - 2):
            take = min(counts[idx], counts[idx + 1], counts[idx + 2])
            if take:
                counts[idx] -= take
                counts[idx + 1] -= take
                counts[idx + 2] -= take
                melds += take
                made += take
        if made == 0:
            break
    return melds


def _estimate_melds_and_pair(counts: Sequence[int]) -> Tuple[int, bool, int]:
    """Estimate meld count, whether a pair exists, and the singles penalty."""

    # The singles penalty must be computed from the original histogram to match the
    # behaviour of the pre-refactor implementation.
    singles = sum(1 for value in counts if value == 1)
    mutable = list(counts)
    melds = _remove_triplets(mutable)
    melds += _remove_sequences(mutable, 0)
    melds += _remove_sequences(mutable, 9)
    melds += _remove_sequences(mutable, 18)

    has_pair = any(value >= 2 for value in mutable)
    return melds, has_pair, singles


def _count_fixed_melds(melds: Optional[Sequence[dict]]) -> int:
    """Number of exposed melds present in the observation."""

    if not melds:
        return 0
    exposed = {"CHI", "PONG", "GANG"}
    return sum(1 for meld in melds if (meld.get("type") or "").upper() in exposed)


def _heuristic(hand: Sequence[Tile], melds: Optional[Sequence[dict]]) -> HeuristicSnapshot:
    """Compute heuristic metrics for the current hand state."""

    fixed_melds = _count_fixed_melds(melds)
    need = max(0, 5 - fixed_melds)  # Taiwan 16 uses 5 melds
    counts = _counts34(hand)
    melds_from_hand, has_pair, singles = _estimate_melds_and_pair(counts)

    missing_melds = max(0, need - melds_from_hand)
    missing_eye = 0 if has_pair else 1
    cost = missing_melds * 10 + missing_eye * 3 + min(3, singles)
    return HeuristicSnapshot(cost, melds_from_hand, has_pair, singles)


def _copy_melds(melds: Optional[Sequence[dict]]) -> List[dict]:
    return [dict(meld) for meld in (melds or [])]


def _after_discard(obs: dict, action: dict) -> Tuple[List[Tile], List[dict]]:
    """Simulate the (hand, melds) tuple after a DISCARD action."""

    hand = list(obs.get("hand") or [])
    drawn = obs.get("drawn")
    melds = _copy_melds(obs.get("melds"))

    tile = action.get("tile")
    source = action.get("from", "hand")

    if source != "drawn":
        if tile in hand:
            hand.remove(tile)
        if drawn is not None:
            hand.append(drawn)

    return hand, melds


def _remove_tiles(hand: MutableSequence[Tile], tile: Tile, amount: int) -> None:
    removed = 0
    for idx in range(len(hand) - 1, -1, -1):
        if hand[idx] == tile:
            hand.pop(idx)
            removed += 1
            if removed == amount:
                return


def _after_claim(obs: dict, action: dict) -> Tuple[List[Tile], List[dict]]:
    """Simulate (hand, melds) after claiming CHI/PONG/GANG."""

    hand = list(obs.get("hand") or [])
    melds = _copy_melds(obs.get("melds"))
    last_discard = obs.get("last_discard") or {}
    tile = last_discard.get("tile")
    claim_type = (action.get("type") or "").upper()

    if claim_type == "CHI":
        a, b = action.get("use", [None, None])
        if a in hand:
            hand.remove(a)
        if b in hand:
            hand.remove(b)
        melds.append({"type": "CHI", "tiles": [a, b, tile]})
    elif claim_type == "PONG":
        _remove_tiles(hand, tile, 2)
        melds.append({"type": "PONG", "tiles": [tile] * 3})
    elif claim_type == "GANG":
        _remove_tiles(hand, tile, 3)
        melds.append({"type": "GANG", "tiles": [tile] * 4})

    return hand, melds


class GreedyBotStrategy:
    """Heuristic-driven bot that focuses on shape instead of points."""

    def choose(self, obs: dict) -> dict:
        """Choose an action using the greedy heuristic; HU if available."""

        actions = obs.get("legal_actions", []) or []
        if not actions:
            return {"type": "PASS"}

        for action in actions:
            if (action.get("type") or "").upper() == "HU":
                return action

        phase = obs.get("phase")
        if phase == "REACTION":
            return self._choose_reaction(obs, actions)
        return self._choose_turn(obs, actions)

    # ------------------------------------------------------------------
    # Decision helpers

    def _choose_reaction(self, obs: dict, actions: Sequence[dict]) -> dict:
        baseline = _heuristic(obs.get("hand") or [], obs.get("melds"))
        best_action = {"type": "PASS"}
        best_key = (baseline.cost, 1)

        for action in actions:
            claim_type = (action.get("type") or "").upper()
            if claim_type not in {"CHI", "PONG", "GANG"}:
                continue

            hand, melds = _after_claim(obs, action)
            snapshot = _heuristic(hand, melds)
            priority = 0 if claim_type == "GANG" else 1
            key = (snapshot.cost, priority)
            if key < best_key:
                best_action = action
                best_key = key

        return best_action

    def _choose_turn(self, obs: dict, actions: Sequence[dict]) -> dict:
        tings = [a for a in actions if (a.get("type") or "").upper() == "TING"]
        if tings:
            return max(tings, key=lambda action: len(action.get("waits") or []))

        best_action: Optional[dict] = None
        best_key: Optional[Tuple[int, int]] = None

        for action in actions:
            if (action.get("type") or "").upper() != "DISCARD":
                continue

            hand, melds = _after_discard(obs, action)
            snapshot = _heuristic(hand, melds)
            tie_break = 0
            label = tile_to_str(action.get("tile"))
            if label and len(label) == 1:  # honours: E/S/W/N/C/F/P
                tie_break = -1

            key = (snapshot.cost, tie_break)
            if best_key is None or key < best_key:
                best_action = action
                best_key = key

        return best_action if best_action is not None else actions[0]
