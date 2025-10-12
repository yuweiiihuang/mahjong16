"""Deprecated compatibility layer for legacy imports."""
from __future__ import annotations

import warnings

warnings.warn(
    "The 'core' package is deprecated; import from 'sdk' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from sdk import (  # noqa: F401
    Action,
    DiscardPublic,
    Mahjong16Env,
    MahjongEnvironment,
    MeldPublic,
    Observation,
    Ruleset,
    Tile,
    chi_options,
    flower_ids,
    full_wall,
    hand_to_str,
    is_flower,
    is_win_16,
    load_rule_profile,
    tile_sort_key,
    tile_to_str,
    waits_after_discard_17,
    waits_for_hand_16,
    N_FLOWERS,
    N_TILES,
)

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
