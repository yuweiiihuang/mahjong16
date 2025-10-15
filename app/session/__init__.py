"""Session orchestration and adapter interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .ports import HandSummaryPort, ProgressPort, ScoreState, StepEvent, TableViewPort

if TYPE_CHECKING:  # pragma: no cover - import-time typing helper
    from app.runtime import SessionService as SessionService


def __getattr__(name: str) -> Any:  # pragma: no cover - lightweight accessor
    if name == "SessionService":
        from app.runtime import SessionService as _SessionService

        return _SessionService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SessionService",
    "TableViewPort",
    "HandSummaryPort",
    "ProgressPort",
    "StepEvent",
    "ScoreState",
]
