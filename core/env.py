"""Deprecated shim for :mod:`domain.gameplay.env`."""
from __future__ import annotations

import warnings

from domain.gameplay.env import Mahjong16Env, MahjongEnvironment

warnings.warn(
    "Importing from 'core.env' is deprecated; use 'domain.gameplay.env' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["Mahjong16Env", "MahjongEnvironment"]
