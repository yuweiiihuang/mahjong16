"""Deprecated shim for :mod:`domain.scoring`."""
from __future__ import annotations

import sys
import warnings

from domain.scoring import (
    DerivedScoringState,
    HandState,
    Meld,
    PlayerView,
    ScoringContext,
    ScoringTable,
    WinState,
    build_state,
    compute_payments,
    score_with_breakdown,
)
from domain.scoring import (
    breakdown as _breakdown,
    common as _common,
    engine as _engine,
    rules as _rules,
    state as _state,
    tables as _tables,
    types as _types,
    utils as _utils,
)

warnings.warn(
    "Importing from 'core.scoring' is deprecated; use 'domain.scoring' instead.",
    DeprecationWarning,
    stacklevel=2,
)

sys.modules[__name__ + ".breakdown"] = _breakdown
sys.modules[__name__ + ".common"] = _common
sys.modules[__name__ + ".engine"] = _engine
sys.modules[__name__ + ".rules"] = _rules
sys.modules[__name__ + ".state"] = _state
sys.modules[__name__ + ".tables"] = _tables
sys.modules[__name__ + ".types"] = _types
sys.modules[__name__ + ".utils"] = _utils

__all__ = [
    "compute_payments",
    "score_with_breakdown",
    "build_state",
    "DerivedScoringState",
    "HandState",
    "WinState",
    "Meld",
    "PlayerView",
    "ScoringContext",
    "ScoringTable",
]
