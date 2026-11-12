import pytest

from domain.rules import Ruleset
from domain.rules.hands import is_win_16, waits_for_hand_16
from domain.tiles import Tile


# Five chows and an east pair; existing melds replace the final chow.
CHOWS = list(range(15))
PONGS = [{"type": "PONG", "tiles": [tile] * 3} for tile in range(0, 27, 5)]


@pytest.mark.parametrize(
    "tiles,melds,expected",
    [
        pytest.param(CHOWS + [Tile.E] * 2, [], True, id="five-chows"),
        pytest.param(CHOWS[:-1] + [Tile.E] * 2, [], False, id="missing-tile"),
        pytest.param(CHOWS + [Tile.E, Tile.S], [], False, id="no-pair"),
        pytest.param([7, 8, 9] + list(range(12, 24)) + [Tile.E] * 2,
                     [], False, id="cross-suit-chow"),
        pytest.param(list(range(12)) + [Tile.E, Tile.S, Tile.W] + [Tile.N] * 2,
                     [], False, id="honors-are-not-a-chow"),
        *[
            pytest.param(CHOWS[:-3] + [Tile.E] * 2,
                         [{"type": kind, "tiles": [Tile.B9] * size}], True, id=kind)
            for kind, size in (("PONG", 3), ("ANGANG", 4))
        ],
        # Copies per tile are not capped: five easts split as a pong plus the pair.
        pytest.param(CHOWS[:12] + [Tile.E] * 5, [], True, id="five-honor-copies"),
        pytest.param(CHOWS[:12] + [Tile.E] * 4 + [Tile.S], [], False,
                     id="four-honors-are-not-a-meld"),
        pytest.param([Tile.S] * 2, PONGS[:5], True, id="five-open-melds-pair"),
        pytest.param([Tile.S, Tile.W], PONGS[:5], False, id="five-open-melds-no-pair"),
        pytest.param([Tile.S] * 2, PONGS[:6], False, id="six-open-melds"),
        pytest.param(CHOWS + [Tile.E] * 2, [{"type": "FLOWER", "tiles": [Tile.B9] * 3}],
                     True, id="unknown-meld-type-ignored"),
        pytest.param(CHOWS + [Tile.E, -1], [], False, id="negative-id"),
        pytest.param(CHOWS + [Tile.E, 34], [], False, id="flower-id"),
        pytest.param(CHOWS + [Tile.E] * 3, [], False, id="one-tile-too-many"),
    ],
)
def test_is_win_16_requires_melds_and_a_pair(tiles, melds, expected):
    assert is_win_16(tiles, melds, Ruleset(include_flowers=False)) is expected


@pytest.mark.parametrize(
    "hand16,exclude_exhausted,expected",
    [
        # Waits across the 萬/筒 boundary: 8 and 9 are neighbours by id, not by suit.
        pytest.param(CHOWS[:12] + [9] + [Tile.E] * 3, True, [9, 12], id="pair-or-edge"),
        pytest.param(CHOWS + [Tile.E], True, [Tile.E], id="isolated-honor-pair-wait"),
        # The fifth east only counts when exhausted tiles are kept, as in single-wait scoring.
        pytest.param(CHOWS[:12] + [Tile.E] * 4, False, [Tile.E], id="fifth-copy-wait"),
        pytest.param(CHOWS[:12] + [Tile.E] * 4, True, [], id="exhausted-wait-excluded"),
        pytest.param(CHOWS + [34], True, [], id="flower-in-hand"),
    ],
)
def test_waits_for_hand_16(hand16, exclude_exhausted, expected):
    rules = Ruleset(include_flowers=False)
    assert waits_for_hand_16(hand16, [], rules, exclude_exhausted=exclude_exhausted) == expected
