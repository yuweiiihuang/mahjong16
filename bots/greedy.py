"""Greedy bot for smoke tests.

The strategy is intentionally light-weight: it evaluates candidate actions with a
hand-shape heuristic that approximates how many melds and pairs can be formed.
The bot is not meant to be strong, but it provides deterministic behaviour that
is useful for unit tests and manual debugging.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, List, MutableSequence, Optional, Sequence, Tuple

from core.tiles import tile_to_str


# ---------------------------------------------------------------------------
# Typed helpers


Tile = int


@dataclass(frozen=True)
class HeuristicSnapshot:
    """Summary of the heuristic evaluation for a hand state."""

    cost: int
    structure_distance: int
    melds: int
    eye_used: bool
    bad_shapes: int
    isolated: int


@dataclass(frozen=True)
class HeuristicWeights:
    """Tunables used by the greedy heuristic."""

    structure_weight: int = 100      # Dominant weight for structure distance
    bad_shape_weight: int = 5        # Penalty per bad structure (劣形搭子)
    isolated_weight: int = 1         # Penalty per isolated tile (孤張)
    isolated_cap: int = 14           # Safety cap for isolated penalty

    def evaluate(self, structure_distance: int, bad_shapes: int, isolated: int) -> int:
        isolated_penalty = min(self.isolated_cap, isolated) * self.isolated_weight
        return (
            structure_distance * self.structure_weight
            + bad_shapes * self.bad_shape_weight
            + isolated_penalty
        )


_DEFAULT_WEIGHTS = HeuristicWeights()


def _counts34(tiles: Iterable[Tile]) -> List[int]:
    """Map tiles into the standard 34-tile histogram."""

    counts = [0] * 34
    for tile in tiles:
        if 0 <= tile < 34:
            counts[tile] += 1
    return counts


@dataclass(frozen=True)
class ShapeState:
    """Intermediate partition of the concealed tiles within a suit block."""

    melds: int = 0
    good_partials: int = 0
    bad_partials: int = 0
    pairs: int = 0
    singles: int = 0

    def with_delta(
        self,
        *,
        melds: int = 0,
        good_partials: int = 0,
        bad_partials: int = 0,
        pairs: int = 0,
        singles: int = 0,
    ) -> "ShapeState":
        return ShapeState(
            self.melds + melds,
            self.good_partials + good_partials,
            self.bad_partials + bad_partials,
            self.pairs + pairs,
            self.singles + singles,
        )

    def __add__(self, other: "ShapeState") -> "ShapeState":
        return ShapeState(
            self.melds + other.melds,
            self.good_partials + other.good_partials,
            self.bad_partials + other.bad_partials,
            self.pairs + other.pairs,
            self.singles + other.singles,
        )


def _pareto_sort_key(state: ShapeState) -> Tuple[int, int, int, int, int]:
    """Order states so that more promising ones are considered first."""

    return (
        -state.melds,
        -state.good_partials,
        state.bad_partials,
        -state.pairs,
        state.singles,
    )


def _dominates(a: ShapeState, b: ShapeState) -> bool:
    """Return True if state ``a`` (weakly) dominates ``b`` with a strict gain."""

    if not (
        a.melds >= b.melds
        and a.good_partials >= b.good_partials
        and a.bad_partials <= b.bad_partials
        and a.pairs >= b.pairs
        and a.singles <= b.singles
    ):
        return False
    return (
        a.melds > b.melds
        or a.good_partials > b.good_partials
        or a.bad_partials < b.bad_partials
        or a.pairs > b.pairs
        or a.singles < b.singles
    )


def _pareto_prune(states: Iterable[ShapeState]) -> Tuple[ShapeState, ...]:
    """Remove dominated states to keep the Cartesian expansion manageable."""

    ordered = sorted(set(states), key=_pareto_sort_key)
    frontier: List[ShapeState] = []
    for candidate in ordered:
        dominated = False
        to_remove: List[int] = []
        for idx, keep in enumerate(frontier):
            if _dominates(keep, candidate):
                dominated = True
                break
            if _dominates(candidate, keep):
                to_remove.append(idx)
        if dominated:
            continue
        for idx in reversed(to_remove):
            frontier.pop(idx)
        frontier.append(candidate)
    return tuple(frontier)


def _count_fixed_melds(melds: Optional[Sequence[dict]]) -> int:
    """Number of exposed melds present in the observation."""

    if not melds:
        return 0
    exposed = {"CHI", "PONG", "GANG"}
    return sum(1 for meld in melds if (meld.get("type") or "").upper() in exposed)


@lru_cache(maxsize=None)
def _analyze_suit(tuple_counts: Tuple[int, ...]) -> Tuple[ShapeState, ...]:
    """Enumerate possible partitions for a suit (萬/筒/條)."""

    try:
        idx = next(i for i, value in enumerate(tuple_counts) if value)
    except StopIteration:
        return (ShapeState(),)

    counts = list(tuple_counts)
    results: set[ShapeState] = set()

    # Treat current tile as a single
    counts[idx] -= 1
    for state in _analyze_suit(tuple(counts)):
        results.add(state.with_delta(singles=1))
    counts[idx] += 1

    # Pair (could be used as eyes or triplet candidate)
    if counts[idx] >= 2:
        counts[idx] -= 2
        for state in _analyze_suit(tuple(counts)):
            results.add(state.with_delta(pairs=1))
        counts[idx] += 2

    # Triplet (complete meld)
    if counts[idx] >= 3:
        counts[idx] -= 3
        for state in _analyze_suit(tuple(counts)):
            results.add(state.with_delta(melds=1))
        counts[idx] += 3

    # Sequence (complete meld)
    if idx <= len(counts) - 3 and counts[idx + 1] and counts[idx + 2]:
        counts[idx] -= 1
        counts[idx + 1] -= 1
        counts[idx + 2] -= 1
        for state in _analyze_suit(tuple(counts)):
            results.add(state.with_delta(melds=1))
        counts[idx] += 1
        counts[idx + 1] += 1
        counts[idx + 2] += 1

    # Consecutive partial (open wait)
    if idx <= len(counts) - 2 and counts[idx + 1]:
        counts[idx] -= 1
        counts[idx + 1] -= 1
        is_edge = idx == 0 or (idx + 1) == 8
        delta_good = 0 if is_edge else 1
        delta_bad = 1 if is_edge else 0
        for state in _analyze_suit(tuple(counts)):
            results.add(
                state.with_delta(
                    good_partials=delta_good,
                    bad_partials=delta_bad,
                )
            )
        counts[idx] += 1
        counts[idx + 1] += 1

    # Gapped partial (kanchan)
    if idx <= len(counts) - 3 and counts[idx + 2]:
        counts[idx] -= 1
        counts[idx + 2] -= 1
        for state in _analyze_suit(tuple(counts)):
            results.add(state.with_delta(bad_partials=1))
        counts[idx] += 1
        counts[idx + 2] += 1

    return _pareto_prune(results)


def _analyze_honors(tuple_counts: Tuple[int, ...]) -> ShapeState:
    """Deterministic partition for honors (風/箭)."""

    melds = 0
    pairs = 0
    singles = 0
    for value in tuple_counts:
        melds += value // 3
        remainder = value % 3
        if remainder == 2:
            pairs += 1
        elif remainder == 1:
            singles += 1
    return ShapeState(melds, 0, 0, pairs, singles)


def _combine_shape_states(states_per_block: Sequence[Tuple[ShapeState, ...]]) -> Tuple[ShapeState, ...]:
    combined: set[ShapeState] = {ShapeState()}
    for block_states in states_per_block:
        next_combined: set[ShapeState] = set()
        for current in combined:
            for candidate in block_states:
                next_combined.add(current + candidate)
        combined = next_combined
    return _pareto_prune(combined)


def _hand_shape_states(counts: Sequence[int]) -> Tuple[ShapeState, ...]:
    """Return possible aggregate partitions of the concealed hand."""

    wan = _analyze_suit(tuple(counts[0:9]))
    tong = _analyze_suit(tuple(counts[9:18]))
    tiao = _analyze_suit(tuple(counts[18:27]))
    honors = _analyze_honors(tuple(counts[27:34]))
    combined = _combine_shape_states((wan, tong, tiao))
    return _pareto_prune(state + honors for state in combined)


def _score_shape_state(
    state: ShapeState,
    fixed_melds: int,
    use_eye: int,
    weights: HeuristicWeights,
) -> HeuristicSnapshot:
    total_melds = fixed_melds + state.melds
    missing_meld_slots = max(0, 5 - total_melds)

    good_used = min(state.good_partials, missing_meld_slots)
    remaining = missing_meld_slots - good_used

    bad_used = min(state.bad_partials, remaining)
    remaining -= bad_used

    available_pairs = max(0, state.pairs - use_eye)
    pair_used = min(available_pairs, remaining)
    remaining -= pair_used

    candidates_total = good_used + bad_used + pair_used
    structure_distance = max(0, 5 - total_melds - candidates_total)
    bad_shapes = state.bad_partials + max(0, state.pairs - use_eye)
    isolated = state.singles

    cost = weights.evaluate(structure_distance, bad_shapes, isolated)
    return HeuristicSnapshot(
        cost=cost,
        structure_distance=structure_distance,
        melds=total_melds,
        eye_used=bool(use_eye),
        bad_shapes=bad_shapes,
        isolated=isolated,
    )


def _heuristic(
    hand: Sequence[Tile],
    melds: Optional[Sequence[dict]],
    weights: HeuristicWeights = _DEFAULT_WEIGHTS,
) -> HeuristicSnapshot:
    """Compute heuristic metrics for the current hand state."""

    fixed_melds = _count_fixed_melds(melds)
    counts = _counts34(hand)
    shape_states = _hand_shape_states(counts)

    best_snapshot: Optional[HeuristicSnapshot] = None
    for state in shape_states:
        for use_eye in (0, 1) if state.pairs > 0 else (0,):
            snapshot = _score_shape_state(state, fixed_melds, use_eye, weights)
            if best_snapshot is None or snapshot.cost < best_snapshot.cost:
                best_snapshot = snapshot

    if best_snapshot is None:
        # Fallback: empty hand (should not occur for valid states)
        best_snapshot = HeuristicSnapshot(
            cost=0,
            structure_distance=5,
            melds=fixed_melds,
            eye_used=False,
            bad_shapes=0,
            isolated=0,
        )
    return best_snapshot


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

    def __init__(self, weights: Optional[HeuristicWeights] = None) -> None:
        self.weights = weights or HeuristicWeights()

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
        baseline = _heuristic(obs.get("hand") or [], obs.get("melds"), self.weights)
        best_action = {"type": "PASS"}
        best_key = (baseline.cost, 1)

        for action in actions:
            claim_type = (action.get("type") or "").upper()
            if claim_type not in {"CHI", "PONG", "GANG"}:
                continue

            hand, melds = _after_claim(obs, action)
            snapshot = _heuristic(hand, melds, self.weights)
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
            snapshot = _heuristic(hand, melds, self.weights)
            tie_break = 0
            label = tile_to_str(action.get("tile"))
            if label and len(label) == 1:  # honours: E/S/W/N/C/F/P
                tie_break = -1

            key = (snapshot.cost, tie_break)
            if best_key is None or key < best_key:
                best_action = action
                best_key = key

        return best_action if best_action is not None else actions[0]
