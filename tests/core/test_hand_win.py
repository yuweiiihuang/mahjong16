import pytest

from domain.rules import Ruleset
from domain.rules.hands import is_win_16
from domain.tiles import Tile


# Five chows and an east pair; existing melds replace the final chow.
CHOWS = list(range(15))


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
    ],
)
def test_is_win_16_requires_melds_and_a_pair(tiles, melds, expected):
    assert is_win_16(tiles, melds, Ruleset(include_flowers=False)) is expected
