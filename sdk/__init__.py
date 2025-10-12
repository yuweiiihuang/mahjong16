"""Mahjong16 public SDK surface.

This module acts as the supported import gateway for third-party extensions.
Consumers should rely on the objects exported here instead of reaching into
internal ``domain`` or ``app`` packages directly. The SDK deliberately
re-exports gameplay primitives, scoring helpers, and session orchestration
utilities that are stable across releases.
"""

from __future__ import annotations

from domain import (
    Mahjong16Env,
    MahjongEnvironment,
    Ruleset,
    Tile,
    chi_options,
    flower_ids,
    full_wall,
    hand_to_str,
    is_flower,
    load_rule_profile,
    tile_sort_key,
    tile_to_str,
    N_FLOWERS,
    N_TILES,
)
from domain.gameplay.types import Action, DiscardPublic, MeldPublic, Observation
from domain.rules.hands import is_win_16, waits_after_discard_17, waits_for_hand_16
from domain.scoring.engine import compute_payments, score_with_breakdown
from domain.scoring.tables import ScoringTable, load_scoring_assets
from domain.scoring.types import ScoringContext
from typing import TYPE_CHECKING, Any, Callable, Dict

if TYPE_CHECKING:  # pragma: no cover - import-time typing helpers only
    from app.runtime import (
        build_headless_session as _BuildHeadlessSession,
        build_ui_session as _BuildUiSession,
        run_demo as _RunDemo,
        run_demo_headless as _RunDemoHeadless,
        run_demo_headless_batch as _RunDemoHeadlessBatch,
        run_demo_headless_collect as _RunDemoHeadlessCollect,
        run_demo_ui as _RunDemoUi,
    )
    from app.session import (
        HandSummaryPort as _HandSummaryPort,
        ProgressPort as _ProgressPort,
        ScoreState as _ScoreState,
        SessionService as _SessionService,
        StepEvent as _StepEvent,
        TableViewPort as _TableViewPort,
    )
    from app.strategies import Strategy as _Strategy, build_strategies as _BuildStrategies
    from app.table import TableManager as _TableManager


def _load_analysis_exports() -> Dict[str, Any]:
    from core.analysis import (
        simulate_after_discard as _simulate_after_discard,
        visible_count_after as _visible_count_after,
        visible_count_global as _visible_count_global,
    )

    return {
        "simulate_after_discard": _simulate_after_discard,
        "visible_count_after": _visible_count_after,
        "visible_count_global": _visible_count_global,
    }


def _load_session_exports() -> Dict[str, Any]:
    from app.session import (
        HandSummaryPort as _HandSummaryPort,
        ProgressPort as _ProgressPort,
        ScoreState as _ScoreState,
        SessionService as _SessionService,
        StepEvent as _StepEvent,
        TableViewPort as _TableViewPort,
    )

    return {
        "HandSummaryPort": _HandSummaryPort,
        "ProgressPort": _ProgressPort,
        "ScoreState": _ScoreState,
        "SessionService": _SessionService,
        "StepEvent": _StepEvent,
        "TableViewPort": _TableViewPort,
    }


def _load_table_manager() -> Any:
    from app.table import TableManager as _TableManager

    return _TableManager


def _load_strategy_exports() -> Dict[str, Any]:
    from app.strategies import Strategy as _Strategy, build_strategies as _BuildStrategies

    return {"Strategy": _Strategy, "build_strategies": _BuildStrategies}


def _load_runtime_exports() -> Dict[str, Any]:
    from app.runtime import (
        build_headless_session as _BuildHeadlessSession,
        build_ui_session as _BuildUiSession,
        run_demo as _RunDemo,
        run_demo_headless as _RunDemoHeadless,
        run_demo_headless_batch as _RunDemoHeadlessBatch,
        run_demo_headless_collect as _RunDemoHeadlessCollect,
        run_demo_ui as _RunDemoUi,
    )

    return {
        "build_headless_session": _BuildHeadlessSession,
        "build_ui_session": _BuildUiSession,
        "run_demo": _RunDemo,
        "run_demo_headless": _RunDemoHeadless,
        "run_demo_headless_batch": _RunDemoHeadlessBatch,
        "run_demo_headless_collect": _RunDemoHeadlessCollect,
        "run_demo_ui": _RunDemoUi,
    }


_LAZY_LOADERS: Dict[str, Callable[[], Any]] = {
    "simulate_after_discard": lambda: _load_analysis_exports()["simulate_after_discard"],
    "visible_count_after": lambda: _load_analysis_exports()["visible_count_after"],
    "visible_count_global": lambda: _load_analysis_exports()["visible_count_global"],
    "HandSummaryPort": lambda: _load_session_exports()["HandSummaryPort"],
    "ProgressPort": lambda: _load_session_exports()["ProgressPort"],
    "ScoreState": lambda: _load_session_exports()["ScoreState"],
    "SessionService": lambda: _load_session_exports()["SessionService"],
    "StepEvent": lambda: _load_session_exports()["StepEvent"],
    "TableViewPort": lambda: _load_session_exports()["TableViewPort"],
    "TableManager": _load_table_manager,
    "Strategy": lambda: _load_strategy_exports()["Strategy"],
    "build_strategies": lambda: _load_strategy_exports()["build_strategies"],
    "build_headless_session": lambda: _load_runtime_exports()["build_headless_session"],
    "build_ui_session": lambda: _load_runtime_exports()["build_ui_session"],
    "run_demo": lambda: _load_runtime_exports()["run_demo"],
    "run_demo_headless": lambda: _load_runtime_exports()["run_demo_headless"],
    "run_demo_headless_batch": lambda: _load_runtime_exports()["run_demo_headless_batch"],
    "run_demo_headless_collect": lambda: _load_runtime_exports()["run_demo_headless_collect"],
    "run_demo_ui": lambda: _load_runtime_exports()["run_demo_ui"],
}


def __getattr__(name: str) -> Any:
    loader = _LAZY_LOADERS.get(name)
    if loader is not None:
        value = loader()
        globals()[name] = value
        return value
    raise AttributeError(f"module 'sdk' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals().keys()))

__all__ = [
    # Gameplay / rules primitives
    "Mahjong16Env",
    "MahjongEnvironment",
    "Ruleset",
    "Tile",
    "Action",
    "Observation",
    "DiscardPublic",
    "MeldPublic",
    "chi_options",
    "flower_ids",
    "full_wall",
    "hand_to_str",
    "is_flower",
    "load_rule_profile",
    "tile_sort_key",
    "tile_to_str",
    "waits_after_discard_17",
    "waits_for_hand_16",
    "is_win_16",
    "N_FLOWERS",
    "N_TILES",
    # Analysis helpers
    "simulate_after_discard",
    "visible_count_after",
    "visible_count_global",
    # Scoring accessors
    "compute_payments",
    "score_with_breakdown",
    "load_scoring_assets",
    "ScoringTable",
    "ScoringContext",
    # Session orchestration & strategies
    "SessionService",
    "StepEvent",
    "ScoreState",
    "TableViewPort",
    "HandSummaryPort",
    "ProgressPort",
    "TableManager",
    "Strategy",
    "build_strategies",
    "build_ui_session",
    "build_headless_session",
    "run_demo",
    "run_demo_ui",
    "run_demo_headless",
    "run_demo_headless_collect",
    "run_demo_headless_batch",
]
