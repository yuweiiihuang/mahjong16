"""Deprecated shim for :mod:`domain.gameplay.player_state`."""
from __future__ import annotations

import warnings

from domain.gameplay.player_state import PlayerState

warnings.warn(
    "Importing from 'core.state' is deprecated; use 'domain.gameplay.player_state' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["PlayerState"]
