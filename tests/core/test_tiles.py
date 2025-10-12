"""Tests for tile helper utilities."""

from sdk import Tile, chi_options


def test_chi_options_returns_empty_for_honors() -> None:
    hand = [int(Tile.W1), int(Tile.W2), int(Tile.W3)]
    assert chi_options(int(Tile.E), hand) == []


def test_chi_options_low_rank_edge() -> None:
    hand = [int(Tile.W2), int(Tile.W3), int(Tile.W4)]
    assert chi_options(int(Tile.W1), hand) == [
        (int(Tile.W2), int(Tile.W3))
    ]


def test_chi_options_high_rank_edge() -> None:
    hand = [int(Tile.B6), int(Tile.B7), int(Tile.B8)]
    assert chi_options(int(Tile.B9), hand) == [
        (int(Tile.B7), int(Tile.B8))
    ]


def test_chi_options_middle_rank_multiple_patterns() -> None:
    hand = [int(Tile.D3), int(Tile.D4), int(Tile.D6), int(Tile.D7)]
    assert chi_options(int(Tile.D5), hand) == [
        (int(Tile.D3), int(Tile.D4)),
        (int(Tile.D4), int(Tile.D6)),
        (int(Tile.D6), int(Tile.D7)),
    ]
