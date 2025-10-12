"""Deprecated shim for :mod:`domain.gameplay.flowers`."""
from __future__ import annotations

import warnings

from domain.gameplay.flowers import FlowerManager, FlowerOutcome

warnings.warn(
    "Importing from 'core.flowers' is deprecated; use 'domain.gameplay.flowers' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["FlowerManager", "FlowerOutcome"]
