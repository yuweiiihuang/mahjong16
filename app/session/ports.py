from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from domain import Mahjong16Env


ScoreState = Dict[str, List[int]]


@dataclass
class StepEvent:
    """Encapsulate information about a processed environment step."""

    observation: Dict[str, Any]
    info: Optional[Dict[str, Any]]
    action: Dict[str, Any]
    acting_pid: Optional[int]
    action_type: str
    discarded_tile: Optional[int]


class TableViewPort(Protocol):
    """Interface for rendering turn-by-turn table updates."""

    def on_session_start(self, *, env: Mahjong16Env, score_state: ScoreState) -> None:
        """Notify that a session is beginning."""

    def on_hand_start(
        self,
        *,
        hand_index: int,
        jang_index: int,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        """Notify that a new hand has started."""

    def on_step(
        self,
        *,
        event: StepEvent,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        """Provide the result of an environment step for rendering."""

    def on_hand_scored(
        self,
        *,
        hand_index: int,
        breakdown: Dict[int, List[Dict[str, Any]]],
        payments: List[int],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        """Deliver scoring results for a completed hand."""

    def on_session_end(
        self,
        *,
        summaries: List[Dict[str, Any]],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        """Notify that the session has completed."""


class HandSummaryPort(Protocol):
    """Interface for persisting or presenting per-hand summaries."""

    def on_hand_summary(self, summary: Dict[str, Any]) -> None:
        """Handle a newly generated hand summary."""

    def finalize(self, summaries: List[Dict[str, Any]]) -> None:
        """Finalize once the session concludes."""


class ProgressPort(Protocol):
    """Interface for reporting hand-level progress."""

    def on_session_start(self, total_hands: Optional[int]) -> None:
        """Prepare any progress indicators for a new session."""

    def on_hand_complete(self, hand_index: int) -> None:
        """Update the progress indicator after a hand completes."""

    def on_session_end(self) -> None:
        """Tear down the progress indicator when the session ends."""


__all__ = [
    "ScoreState",
    "StepEvent",
    "TableViewPort",
    "HandSummaryPort",
    "ProgressPort",
]
