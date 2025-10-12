from __future__ import annotations

from bots.greedy import (
    GreedyBotStrategy,
    HeuristicWeights,
    _heuristic,
    _live_counts_from_obs,
)
from domain.tiles import Tile


def _snapshot(*tiles: Tile):
    hand = [int(t) for t in tiles]
    return _heuristic(hand, melds=None, weights=HeuristicWeights())


def test_structure_distance_minus_one_for_complete_five_meld_hand():
    snapshot = _snapshot(
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D5, Tile.D6,
        Tile.D7, Tile.D7,
    )
    assert snapshot.structure_distance == -1


def test_structure_distance_zero_for_tenpai_shape():
    snapshot = _snapshot(
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D4,
        Tile.D5, Tile.D6,
    )
    assert snapshot.structure_distance == 0


def test_structure_distance_one_when_missing_taatsu():
    snapshot = _snapshot(
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D4,
        Tile.D5, Tile.B1,
    )
    assert snapshot.structure_distance == 1


def test_structure_distance_zero_when_missing_head_with_five_melds():
    snapshot = _snapshot(
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D5, Tile.D6,
        Tile.B1,
    )
    assert snapshot.structure_distance == 0


def test_structure_distance_uses_exposed_melds_in_tenpai():
    hand = [
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D5,
        Tile.D6, Tile.D6,
    ]
    melds = [
        {"type": "CHI", "tiles": [Tile.W1, Tile.W2, Tile.W3]},
        {"type": "CHI", "tiles": [Tile.W4, Tile.W5, Tile.W6]},
    ]
    snapshot = _heuristic(hand, melds=melds, weights=HeuristicWeights())
    assert snapshot.structure_distance == 0


def test_structure_distance_counts_only_one_pair():
    hand = [
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D4,
        Tile.B1, Tile.B1,
    ]
    snapshot = _heuristic(hand, melds=None, weights=HeuristicWeights())
    assert snapshot.structure_distance == 1


def test_availability_zero_for_complete_hand():
    snapshot = _snapshot(
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D5, Tile.D6,
        Tile.D7, Tile.D7,
    )
    assert snapshot.availability == 0


def test_availability_counts_live_waits_in_tenpai():
    hand = [
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D4,
        Tile.D5, Tile.D6,
    ]
    snapshot = _heuristic(hand, melds=None, weights=HeuristicWeights())
    assert snapshot.structure_distance == 0
    assert snapshot.availability == 9


def test_discards_prefer_more_availability_when_structure_equal():
    strategy = GreedyBotStrategy()
    hand = [
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D4,
        Tile.D5, Tile.D6,
    ]
    obs = {
        "phase": "TURN",
        "hand": hand,
        "drawn": Tile.B1,
        "melds": [],
        "melds_all": [[], [], [], []],
        "rivers": [[], [], [], []],
        "legal_actions": [
            {"type": "DISCARD", "tile": Tile.B1, "from": "drawn"},
            {"type": "DISCARD", "tile": Tile.D1, "from": "hand"},
        ],
    }
    action = strategy.choose(obs)
    assert action.get("type") == "DISCARD"
    assert action.get("tile") == Tile.B1


def test_live_counts_use_public_snapshot_when_available():
    base = [4] * 34
    base[Tile.W1] = 2
    base[Tile.D2] = 1
    obs = {
        "hand": [Tile.W1],
        "drawn": Tile.D2,
        "live_public": base,
    }
    counts = _live_counts_from_obs(obs)
    assert counts[Tile.W1] == 1
    assert counts[Tile.D2] == 0
