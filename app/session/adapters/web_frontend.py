"""Table view adapter that streams updates to the web UI bridge."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from domain import Mahjong16Env
from domain.tiles import tile_to_str

from app.session import HandSummaryPort, ScoreState, StepEvent, TableViewPort
from ui.web.bridge import WebSessionBridge
from ui.web.view_model import build_reveal_payload, build_table_state

from .common import summarize_resolved_claim


class WebFrontendAdapter(TableViewPort, HandSummaryPort):
    """Forward session events to the :class:`WebSessionBridge`."""

    def __init__(
        self,
        *,
        bridge: WebSessionBridge,
        human_pid: Optional[int],
        n_players: int,
    ) -> None:
        self.bridge = bridge
        self.human_pid = human_pid
        self.n_players = n_players
        self._discard_id = 0
        self._last_seen_discard: Optional[Tuple[Optional[int], Any]] = None

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------
    def _pov_pid(self) -> int:
        if self.human_pid is None:
            return 0
        return int(self.human_pid)

    def _emit_state(
        self,
        env: Mahjong16Env,
        *,
        score_state: Optional[ScoreState],
        last_action: Optional[Dict[str, str]] = None,
    ) -> None:
        payload = build_table_state(
            env,
            pov_pid=self._pov_pid(),
            discard_id=self._discard_id,
            last_action=last_action,
            score_state=score_state,
        )
        self.bridge.update_base_state(payload)

    # ------------------------------------------------------------------
    # TableViewPort implementation
    # ------------------------------------------------------------------
    def on_session_start(self, *, env: Mahjong16Env, score_state: ScoreState) -> None:
        self.bridge.reset()
        self._discard_id = 0
        self._last_seen_discard = None
        self._emit_state(env, score_state=score_state)

    def on_hand_start(
        self,
        *,
        hand_index: int,
        jang_index: int,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        del hand_index, jang_index
        self._discard_id = 0
        self._last_seen_discard = None
        self.bridge.clear_pending()
        self.bridge.set_reveal(None)
        self._emit_state(env, score_state=score_state)

    def on_step(
        self,
        *,
        event: StepEvent,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        events_to_emit: List[Optional[Dict[str, str]]] = []

        claim_event = summarize_resolved_claim(event.info)
        if claim_event:
            events_to_emit.append(claim_event)

        if event.action_type == "DISCARD" and event.discarded_tile is not None:
            self._discard_id += 1
            self._last_seen_discard = (event.acting_pid, event.discarded_tile)
            events_to_emit.append(
                {
                    "who": f"P{event.acting_pid}",
                    "type": "DISCARD",
                    "detail": tile_to_str(event.discarded_tile),
                }
            )

        if (
            event.observation.get("phase") == "REACTION"
            and self.human_pid is not None
            and event.observation.get("player") == self.human_pid
        ):
            last_discard = getattr(env, "last_discard", None)
            if isinstance(last_discard, dict) and last_discard.get("tile") is not None:
                key = (last_discard.get("pid"), last_discard.get("tile"))
                if key != self._last_seen_discard:
                    self._discard_id += 1
                    self._last_seen_discard = key
                    events_to_emit.append(
                        {
                            "who": f"P{last_discard.get('pid')}",
                            "type": "DISCARD",
                            "detail": tile_to_str(last_discard.get("tile")),
                        }
                    )

        if not events_to_emit:
            events_to_emit.append(None)

        for action in events_to_emit:
            self._emit_state(env, score_state=score_state, last_action=action)

    def on_hand_scored(
        self,
        *,
        hand_index: int,
        breakdown: Dict[int, List[Dict[str, Any]]],
        payments: List[int],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        del hand_index
        reveal = build_reveal_payload(
            env,
            breakdown=breakdown,
            payments=payments,
            totals=score_state.get("totals"),
        )
        self.bridge.set_reveal(reveal)
        self._emit_state(env, score_state=score_state)

    def on_session_end(
        self,
        *,
        summaries: List[Dict[str, Any]],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        del summaries
        self.bridge.clear_pending()
        self._emit_state(env, score_state=score_state)

    # ------------------------------------------------------------------
    # HandSummaryPort implementation
    # ------------------------------------------------------------------
    def on_hand_summary(self, summary: Dict[str, Any]) -> None:
        self.bridge.append_summary(summary)

    def finalize(self, summaries: List[Dict[str, Any]]) -> None:
        del summaries


__all__ = ["WebFrontendAdapter"]
