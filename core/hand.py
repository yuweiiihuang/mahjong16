"""Deprecated shim for :mod:`domain.rules.hands`."""
from __future__ import annotations

import warnings

from domain.rules.hands import is_win_16, waits_after_discard_17, waits_for_hand_16

warnings.warn(
    "Importing from 'core.hand' is deprecated; use 'domain.rules.hands' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["is_win_16", "waits_after_discard_17", "waits_for_hand_16"]
