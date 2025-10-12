"""Mahjong16 package namespace.

This package groups first-party interface adapters that sit on top of the
public :mod:`sdk` surface. External callers should continue to import
functional APIs from :mod:`sdk`; the modules under :mod:`mahjong16.interfaces`
are provided as ready-to-use front ends bundled with the project.
"""

__all__ = ["interfaces"]
