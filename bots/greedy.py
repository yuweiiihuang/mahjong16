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

from core.tiles import N_TILES, tile_to_str


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
    availability: int


@dataclass(frozen=True)
class HeuristicWeights:
    """Tunables used by the greedy heuristic."""

    structure_weight: int = 103      # Dominant weight for structure distance
    bad_shape_weight: int = 5        # Penalty per bad structure (劣形搭子)
    isolated_weight: int = 3         # Penalty per isolated tile (孤張)
    isolated_cap: int = 13           # Safety cap for isolated penalty

    availability_weight: int = 3     # Bonus per live tile improving the hand (活張)

    def evaluate(
        self,
        structure_distance: int,
        bad_shapes: int,
        isolated: int,
        availability: int,
    ) -> int:
        isolated_penalty = min(self.isolated_cap, isolated) * self.isolated_weight
        return (
            structure_distance * self.structure_weight
            + bad_shapes * self.bad_shape_weight
            + isolated_penalty
            - availability * self.availability_weight
        )


_DEFAULT_WEIGHTS = HeuristicWeights()


_MELD_TARGET = 5
_MAX_SHANTEN = _MELD_TARGET * 2


def _weights_cache_key(weights: HeuristicWeights) -> Tuple[int, int, int, int, int]:
    return (
        weights.structure_weight,
        weights.bad_shape_weight,
        weights.isolated_weight,
        weights.isolated_cap,
        weights.availability_weight,
    )


def _counts34(tiles: Iterable[Tile]) -> List[int]:
    """Map tiles into the standard 34-tile histogram."""

    counts = [0] * 34
    for tile in tiles:
        if 0 <= tile < 34:
            counts[tile] += 1
    return counts


def _iter_meld_tiles(meld: dict | Sequence[int]) -> Iterable[Tile]:
    tiles = []
    if isinstance(meld, dict):
        tiles = meld.get("tiles") or []
    else:
        tiles = meld
    for tile in tiles:
        if tile is None:
            continue
        value = int(tile)
        if 0 <= value < N_TILES:
            yield value


def _initial_live_counts() -> List[int]:
    return [4] * N_TILES


def _consume_live_tiles(counts: MutableSequence[int], tiles: Iterable[Tile]) -> None:
    for tile in tiles:
        if tile is None:
            continue
        value = int(tile)
        if 0 <= value < N_TILES and counts[value] > 0:
            counts[value] -= 1


def _default_live_counts(
    hand: Sequence[Tile], melds: Optional[Sequence[dict | Sequence[int]]]
) -> List[int]:
    counts = _initial_live_counts()
    _consume_live_tiles(counts, (int(tile) for tile in hand))

    if melds:
        for meld in melds:
            _consume_live_tiles(counts, _iter_meld_tiles(meld))

    return counts


def _compute_availability(
    counts_key: Tuple[int, ...],
    structure_distance: int,
    live_counts: Sequence[int],
    fixed_melds: int,
    weights_key: Tuple[int, int, int, int, int],
) -> int:
    if structure_distance <= -1:
        return 0

    total = 0
    improving = _improving_tiles(counts_key, fixed_melds, weights_key)
    for tile in improving:
        if 0 <= tile < len(live_counts):
            total += int(live_counts[tile])
    return total


@lru_cache(maxsize=60000)
def _improving_tiles(
    counts_key: Tuple[int, ...],
    fixed_melds: int,
    weights_key: Tuple[int, int, int, int, int],
) -> Tuple[int, ...]:
    base_snapshot = _score_concealed_counts_cached(counts_key, fixed_melds, weights_key)
    base_distance = base_snapshot.structure_distance
    if base_distance <= -1:
        return tuple()

    counts_list = list(counts_key)
    improving: list[int] = []

    candidate_tiles: set[int] = set()
    for tile, count in enumerate(counts_list):
        if count <= 0:
            continue
        candidate_tiles.add(tile)
        if tile < 27:
            base = tile // 9
            for delta in (-2, -1, 1, 2):
                neighbour = tile + delta
                if 0 <= neighbour < 27 and neighbour // 9 == base:
                    candidate_tiles.add(neighbour)

    for tile in candidate_tiles:
        if tile >= N_TILES or counts_list[tile] >= 4:
            continue
        counts_list[tile] += 1
        snapshot = _score_concealed_counts_cached(
            tuple(counts_list),
            fixed_melds,
            weights_key,
        )
        counts_list[tile] -= 1
        if snapshot.structure_distance < base_distance:
            improving.append(tile)
    return tuple(improving)


def _live_counts_from_obs(obs: dict) -> Tuple[int, ...]:
    live_public = obs.get("live_public")
    if live_public is not None:
        counts = [0] * N_TILES
        for idx, value in enumerate(live_public):
            if 0 <= idx < N_TILES:
                counts[idx] = max(0, int(value))
    else:
        counts = _initial_live_counts()
        for melds in obs.get("melds_all") or []:
            for meld in melds or []:
                _consume_live_tiles(counts, _iter_meld_tiles(meld))

        for river in obs.get("rivers") or []:
            _consume_live_tiles(counts, river or [])

    _consume_live_tiles(counts, obs.get("hand") or [])

    drawn = obs.get("drawn")
    if drawn is not None:
        _consume_live_tiles(counts, [drawn])

    return tuple(counts)


def _snapshot_order(snapshot: HeuristicSnapshot) -> Tuple[int, int, int, int]:
    return (
        snapshot.structure_distance,
        -snapshot.availability,
        snapshot.bad_shapes,
        snapshot.isolated,
    )


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


@lru_cache(maxsize=8192)
def _hand_shape_states_cached(counts_key: Tuple[int, ...]) -> Tuple[ShapeState, ...]:
    """Return possible aggregate partitions of the concealed hand."""

    wan = _analyze_suit(tuple(counts_key[0:9]))
    tong = _analyze_suit(tuple(counts_key[9:18]))
    tiao = _analyze_suit(tuple(counts_key[18:27]))
    honors = _analyze_honors(tuple(counts_key[27:34]))
    combined = _combine_shape_states((wan, tong, tiao))
    return _pareto_prune(state + honors for state in combined)


def _score_shape_state(
    state: ShapeState,
    fixed_melds: int,
    use_eye: int,
    weights: HeuristicWeights,
) -> HeuristicSnapshot:
    total_melds = fixed_melds + state.melds
    meld_slots = max(0, _MELD_TARGET - total_melds)

    good_used = min(state.good_partials, meld_slots)
    remaining = meld_slots - good_used

    bad_used = min(state.bad_partials, remaining)
    remaining -= bad_used

    available_pairs = max(0, state.pairs - use_eye)
    taatsu_total = good_used + bad_used
    unused_pairs = available_pairs
    has_head = bool(use_eye or unused_pairs)

    # structure_distance applies a 16-tile shanten-style approximation: the minimum
    # draws to reach tenpai using ``10 - 2m - t - p`` with ``p`` in {0, 1}, plus
    # standard overflow and no-head corrections, mirroring the common
    # five-meld extension of the riichi formula.
    meld_units = total_melds
    partial_units = taatsu_total
    pair_unit = 1 if has_head else 0
    shanten = _MAX_SHANTEN - 2 * meld_units - partial_units - pair_unit
    block_load = meld_units + partial_units
    if block_load > _MELD_TARGET:
        shanten += block_load - _MELD_TARGET
    if pair_unit == 0 and meld_units < _MELD_TARGET:
        shanten += 1

    structure_distance = max(shanten, -1)
    bad_shapes = state.bad_partials + max(0, state.pairs - use_eye)
    isolated = state.singles

    cost = weights.evaluate(structure_distance, bad_shapes, isolated, 0)
    return HeuristicSnapshot(
        cost=cost,
        structure_distance=structure_distance,
        melds=total_melds,
        eye_used=bool(use_eye),
        bad_shapes=bad_shapes,
        isolated=isolated,
        availability=0,
    )


@lru_cache(maxsize=4096)
def _score_concealed_counts_cached(
    counts_key: Tuple[int, ...],
    fixed_melds: int,
    weights_key: Tuple[int, int, int, int, int],
) -> HeuristicSnapshot:
    weights = HeuristicWeights(
        structure_weight=weights_key[0],
        bad_shape_weight=weights_key[1],
        isolated_weight=weights_key[2],
        isolated_cap=weights_key[3],
        availability_weight=weights_key[4],
    )
    shape_states = _hand_shape_states_cached(counts_key)

    best_snapshot: Optional[HeuristicSnapshot] = None
    for state in shape_states:
        for use_eye in (0, 1) if state.pairs > 0 else (0,):
            snapshot = _score_shape_state(state, fixed_melds, use_eye, weights)
            if best_snapshot is None or snapshot.cost < best_snapshot.cost:
                best_snapshot = snapshot

    if best_snapshot is None:
        best_snapshot = HeuristicSnapshot(
            cost=0,
            structure_distance=_MELD_TARGET,
            melds=fixed_melds,
            eye_used=False,
            bad_shapes=0,
            isolated=0,
            availability=0,
        )

    return best_snapshot


def _heuristic(
    hand: Sequence[Tile],
    melds: Optional[Sequence[dict]],
    weights: HeuristicWeights = _DEFAULT_WEIGHTS,
    *,
    live_counts: Optional[Sequence[int]] = None,
    include_availability: bool = True,
) -> HeuristicSnapshot:
    """Compute heuristic metrics for the current hand state."""

    fixed_melds = _count_fixed_melds(melds)
    counts = _counts34(hand)
    counts_key = tuple(counts)
    weights_key = _weights_cache_key(weights)

    best_snapshot = _score_concealed_counts_cached(counts_key, fixed_melds, weights_key)

    if not include_availability:
        return best_snapshot

    live = (
        tuple(live_counts)
        if live_counts is not None
        else tuple(_default_live_counts(hand, melds))
    )
    availability = _compute_availability(
        counts_key,
        best_snapshot.structure_distance,
        live,
        fixed_melds,
        weights_key,
    )
    cost = weights.evaluate(
        best_snapshot.structure_distance,
        best_snapshot.bad_shapes,
        best_snapshot.isolated,
        availability,
    )
    return HeuristicSnapshot(
        cost=cost,
        structure_distance=best_snapshot.structure_distance,
        melds=best_snapshot.melds,
        eye_used=best_snapshot.eye_used,
        bad_shapes=best_snapshot.bad_shapes,
        isolated=best_snapshot.isolated,
        availability=availability,
    )


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
        live_counts = _live_counts_from_obs(obs)

        def make_entry(action: dict, hand: Sequence[Tile], melds: Optional[Sequence[dict]], snapshot: HeuristicSnapshot, priority: int) -> dict:
            return {
                "action": action,
                "hand": hand,
                "melds": melds,
                "snapshot": snapshot,
                "priority": priority,
                "availability_computed": False,
            }

        def ensure_availability(entry: dict) -> None:
            if entry.get("availability_computed"):
                return
            entry["snapshot"] = _heuristic(
                entry["hand"],
                entry["melds"],
                self.weights,
                live_counts=live_counts,
                include_availability=True,
            )
            entry["availability_computed"] = True

        def entry_key(entry: dict) -> Tuple[int, ...]:
            ensure_availability(entry)
            snapshot = entry["snapshot"]
            return _snapshot_order(snapshot) + (snapshot.cost, entry["priority"])

        baseline_hand = list(obs.get("hand") or [])
        baseline_melds = obs.get("melds")
        best_entry = make_entry(
            {"type": "PASS"},
            baseline_hand,
            baseline_melds,
            _heuristic(
                baseline_hand,
                baseline_melds,
                self.weights,
                include_availability=False,
            ),
            1,
        )

        for action in actions:
            claim_type = (action.get("type") or "").upper()
            if claim_type not in {"CHI", "PONG", "GANG"}:
                continue

            hand, melds = _after_claim(obs, action)
            snapshot = _heuristic(
                hand,
                melds,
                self.weights,
                include_availability=False,
            )
            entry = make_entry(
                action,
                hand,
                melds,
                snapshot,
                0 if claim_type == "GANG" else 1,
            )

            best_snapshot = best_entry["snapshot"]
            if snapshot.structure_distance < best_snapshot.structure_distance:
                best_entry = entry
                continue
            if snapshot.structure_distance > best_snapshot.structure_distance:
                continue

            if entry_key(entry) < entry_key(best_entry):
                best_entry = entry

        return best_entry["action"]

    def _choose_turn(self, obs: dict, actions: Sequence[dict]) -> dict:
        tings = [a for a in actions if (a.get("type") or "").upper() == "TING"]
        if tings:
            return max(tings, key=lambda action: len(action.get("waits") or []))

        live_counts = _live_counts_from_obs(obs)

        def ensure_availability(entry: dict) -> None:
            if entry.get("availability_computed"):
                return
            entry["snapshot"] = _heuristic(
                entry["hand"],
                entry["melds"],
                self.weights,
                live_counts=live_counts,
                include_availability=True,
            )
            entry["availability_computed"] = True

        def entry_key(entry: dict) -> Tuple[int, ...]:
            ensure_availability(entry)
            snapshot = entry["snapshot"]
            return _snapshot_order(snapshot) + (snapshot.cost, entry["tie_break"])

        best_entry: Optional[dict] = None

        for action in actions:
            if (action.get("type") or "").upper() != "DISCARD":
                continue

            hand, melds = _after_discard(obs, action)
            snapshot = _heuristic(
                hand,
                melds,
                self.weights,
                include_availability=False,
            )
            label = tile_to_str(action.get("tile"))
            tie_break = -1 if label and len(label) == 1 else 0
            entry = {
                "action": action,
                "hand": hand,
                "melds": melds,
                "snapshot": snapshot,
                "tie_break": tie_break,
                "availability_computed": False,
            }

            if best_entry is None:
                best_entry = entry
                continue

            best_snapshot = best_entry["snapshot"]
            if snapshot.structure_distance < best_snapshot.structure_distance:
                best_entry = entry
                continue
            if snapshot.structure_distance > best_snapshot.structure_distance:
                continue

            if entry_key(entry) < entry_key(best_entry):
                best_entry = entry

        return best_entry["action"] if best_entry is not None else actions[0]
