"""Greedy bot for smoke tests.

The strategy is intentionally light-weight: it evaluates candidate actions with a
hand-shape heuristic that approximates how many melds and pairs can be formed.
The bot is not meant to be strong, but it provides deterministic behaviour that
is useful for unit tests and manual debugging.
"""

from __future__ import annotations

from typing import List, MutableSequence, Optional, Sequence, Tuple

from bots.heuristics import HeuristicSnapshot, Tile, heuristic as _heuristic
from core.tiles import tile_to_str


# ---------------------------------------------------------------------------
# Typed helpers


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
