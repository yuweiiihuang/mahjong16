from __future__ import annotations

from bots.greedy import HeuristicWeights, _heuristic
from core.tiles import Tile


def _snapshot(*tiles: Tile):
    hand = [int(t) for t in tiles]
    return _heuristic(hand, melds=None, weights=HeuristicWeights())


def test_structure_distance_zero_for_complete_five_meld_hand():
    snapshot = _snapshot(
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D5, Tile.D6,
        Tile.D7, Tile.D7,
    )
    assert snapshot.structure_distance == 0


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


def test_structure_distance_one_when_missing_head():
    snapshot = _snapshot(
        Tile.W1, Tile.W2, Tile.W3,
        Tile.W4, Tile.W5, Tile.W6,
        Tile.W7, Tile.W8, Tile.W9,
        Tile.D1, Tile.D2, Tile.D3,
        Tile.D4, Tile.D5, Tile.D6,
        Tile.B1,
    )
    assert snapshot.structure_distance == 1
