from __future__ import annotations

from bots.heuristics import HeuristicSnapshot, heuristic


def _legacy_counts34(tiles):
    counts = [0] * 34
    for tile in tiles:
        if 0 <= tile < 34:
            counts[tile] += 1
    return counts


def _legacy_remove_triplets(counts):
    melds = 0
    for idx, value in enumerate(counts):
        if value >= 3:
            triplets = value // 3
            counts[idx] -= 3 * triplets
            melds += triplets
    return melds


def _legacy_remove_sequences(counts, suit_start):
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


def _legacy_estimate_melds_and_pair(counts):
    singles = sum(1 for value in counts if value == 1)
    mutable = list(counts)
    melds = _legacy_remove_triplets(mutable)
    melds += _legacy_remove_sequences(mutable, 0)
    melds += _legacy_remove_sequences(mutable, 9)
    melds += _legacy_remove_sequences(mutable, 18)
    has_pair = any(value >= 2 for value in mutable)
    return melds, has_pair, singles


def _legacy_count_fixed_melds(melds):
    if not melds:
        return 0
    exposed = {"CHI", "PONG", "GANG"}
    return sum(1 for meld in melds if (meld.get("type") or "").upper() in exposed)


def _legacy_heuristic(hand, melds):
    fixed_melds = _legacy_count_fixed_melds(melds)
    need = max(0, 5 - fixed_melds)
    counts = _legacy_counts34(hand)
    melds_from_hand, has_pair, singles = _legacy_estimate_melds_and_pair(counts)
    missing_melds = max(0, need - melds_from_hand)
    missing_eye = 0 if has_pair else 1
    cost = missing_melds * 10 + missing_eye * 3 + min(3, singles)
    return HeuristicSnapshot(cost, melds_from_hand, has_pair, singles)


def test_heuristic_snapshot_matches_legacy():
    hand = [0, 0, 1, 2, 2, 3, 11, 12, 13, 18, 18, 27, 31, 33]
    melds = [
        {"type": "PONG", "tiles": [4, 4, 4]},
        {"type": "CHI", "tiles": [21, 22, 23]},
    ]

    legacy_snapshot = _legacy_heuristic(hand, melds)
    refactored_snapshot = heuristic(hand, melds)

    assert refactored_snapshot == legacy_snapshot
