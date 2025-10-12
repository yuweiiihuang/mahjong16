"""Domain-level API for Mahjong16 gameplay primitives."""
from __future__ import annotations

from .gameplay.env import MahjongEnvironment, Mahjong16Env
from .rules.ruleset import Ruleset, load_rule_profile
from .tiles import (
    Tile,
    chi_options,
    flower_ids,
    full_wall,
    hand_to_str,
    is_flower,
    tile_sort_key,
    tile_to_str,
    N_FLOWERS,
    N_TILES,
)

__all__ = [
    "MahjongEnvironment",
    "Mahjong16Env",
    "Ruleset",
    "load_rule_profile",
    "Tile",
    "chi_options",
    "flower_ids",
    "full_wall",
    "hand_to_str",
    "is_flower",
    "tile_sort_key",
    "tile_to_str",
    "N_FLOWERS",
    "N_TILES",
]
