"""Deprecated shim for :mod:`domain.gameplay.types`."""
from __future__ import annotations

import warnings

from domain.gameplay.types import Action, DiscardPublic, Observation, MeldPublic

warnings.warn(
    "Importing from 'core.types' is deprecated; use 'domain.gameplay.types' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["Action", "DiscardPublic", "Observation", "MeldPublic"]
