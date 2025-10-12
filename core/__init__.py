"""Deprecated compatibility layer for legacy imports."""
from __future__ import annotations

import warnings

warnings.warn(
    "The 'core' package is deprecated; import from 'domain' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from domain import (  # noqa: F401
    Mahjong16Env,
    MahjongEnvironment,
    Ruleset,
    Tile,
    chi_options,
    flower_ids,
    full_wall,
    hand_to_str,
    is_flower,
    load_rule_profile,
    tile_sort_key,
    tile_to_str,
    N_FLOWERS,
    N_TILES,
)
from domain.rules import (  # noqa: F401
    is_win_16,
    waits_after_discard_17,
    waits_for_hand_16,
)
from domain.gameplay.types import Action, DiscardPublic, Observation, MeldPublic  # noqa: F401

__all__ = [
    "Mahjong16Env",
    "MahjongEnvironment",
    "Ruleset",
    "Tile",
    "chi_options",
    "flower_ids",
    "full_wall",
    "hand_to_str",
    "is_flower",
    "load_rule_profile",
    "tile_sort_key",
    "tile_to_str",
    "N_FLOWERS",
    "N_TILES",
    "is_win_16",
    "waits_after_discard_17",
    "waits_for_hand_16",
    "Action",
    "DiscardPublic",
    "Observation",
    "MeldPublic",
]
