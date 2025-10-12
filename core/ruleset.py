"""Deprecated shim for :mod:`domain.rules.ruleset`."""
from __future__ import annotations

import warnings

from domain.rules.ruleset import Ruleset, load_rule_profile

warnings.warn(
    "Importing from 'core.ruleset' is deprecated; use 'domain.rules.ruleset' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["Ruleset", "load_rule_profile"]
