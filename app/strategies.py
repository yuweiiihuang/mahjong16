"""Compatibility shim forwarding strategy lookups to the bots package."""

from __future__ import annotations

from bots import AutoStrategy, HumanStrategy, Strategy, build_strategies

__all__ = ["Strategy", "AutoStrategy", "HumanStrategy", "build_strategies"]
