"""State coordinator and adapters powering the web UI."""

from __future__ import annotations

import copy
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Tuple

from domain import Mahjong16Env
from domain.gameplay import Observation
from domain.tiles import tile_to_str

from app.session.ports import HandSummaryPort, ScoreState, StepEvent, TableViewPort
from ui.human_common import (
    ReactionContext,
    TurnActionContext,
    TurnActionOption,
    WaitDetail,
    build_reaction_context,
    build_turn_context,
)
from ui.web.state import build_table_payload


def _label_for_wait(wait: WaitDetail) -> Dict[str, Any]:
    return {
        "tile": wait.tile,
        "label": tile_to_str(wait.tile),
        "remaining": wait.remaining,
    }


def _label_for_turn_option(option: TurnActionOption) -> Dict[str, Any]:
    return {
        "tile": option.tile,
        "label": tile_to_str(option.tile),
        "source": option.source,
        "from_drawn": option.from_drawn,
        "waits": [_label_for_wait(wait) for wait in option.waits],
    }


def _timestamp() -> float:
    return time.time()


@dataclass
class PromptData:
    """Book-keeping for the active prompt awaiting user input."""

    prompt_id: int
    payload: Dict[str, Any]
    actions: Dict[str, Dict[str, Any]]


class WebSessionStateManager:
    """Owns the shared state consumed by the web client and strategies."""

    def __init__(self, *, human_pid: int, history_size: int = 200) -> None:
        self.human_pid = human_pid
        self._lock = threading.Lock()
        self._history: Deque[Dict[str, Any]] = deque(maxlen=history_size)
        self._state: Dict[str, Any] = {
            "session": {"status": "idle"},
            "table": None,
            "prompt": None,
            "history": [],
            "hands": [],
        }
        self._state_version = 0
        self._prompt_seq = 0
        self._current_prompt: Optional[PromptData] = None
        self._pending_action: Optional[Dict[str, Any]] = None
        self._action_event = threading.Event()
        self._session_active = False
        self._session_error: Optional[str] = None

    # ---------- Session lifecycle ----------

    def reset_for_session(self) -> None:
        with self._lock:
            self._history.clear()
            self._state = {
                "session": {
                    "status": "running",
                    "started_at": _timestamp(),
                    "hand_index": None,
                    "jang_index": None,
                    "completed_hands": 0,
                },
                "table": None,
                "prompt": None,
                "history": [],
                "hands": [],
            }
            self._session_active = True
            self._session_error = None
            self._state_version += 1
            self._pending_action = None
            self._current_prompt = None
            self._prompt_seq = 0
            self._action_event.clear()

    def finalize_session(self, *, summaries: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._session_active = False
            session_block = self._state.get("session", {})
            session_block["status"] = "complete"
            session_block["ended_at"] = _timestamp()
            self._state["session"] = session_block
            self._state["hands"] = summaries
            self._state_version += 1
            self._action_event.set()

    def session_failed(self, message: str) -> None:
        with self._lock:
            self._session_active = False
            self._session_error = message
            session_block = self._state.get("session", {})
            session_block["status"] = "error"
            session_block["error"] = message
            session_block["ended_at"] = _timestamp()
            self._state["session"] = session_block
            self._state_version += 1
            self._action_event.set()

    # ---------- Table + history updates ----------

    def update_table(
        self,
        env: Mahjong16Env,
        *,
        discard_counter: Optional[int],
        last_action: Optional[Dict[str, Any]],
        score_state: Optional[ScoreState],
    ) -> None:
        payload = build_table_payload(
            env,
            human_pid=self.human_pid,
            discard_counter=discard_counter,
            last_action=last_action,
            score_state=score_state,
        )
        with self._lock:
            self._state["table"] = payload
            self._state_version += 1

    def append_history(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._history.appendleft(entry)
            self._state["history"] = list(self._history)
            self._state_version += 1

    def update_hand_progress(self, *, hand_index: int, jang_index: int) -> None:
        with self._lock:
            session_block = self._state.get("session", {})
            session_block["hand_index"] = hand_index
            session_block["jang_index"] = jang_index
            self._state["session"] = session_block
            self._state_version += 1

    def mark_hand_complete(self, *, summary: Dict[str, Any]) -> None:
        with self._lock:
            session_block = self._state.get("session", {})
            completed = int(session_block.get("completed_hands", 0)) + 1
            session_block["completed_hands"] = completed
            self._state["session"] = session_block
            hands = list(self._state.get("hands", []))
            hands.append(summary)
            self._state["hands"] = hands
            self._state_version += 1

    # ---------- Prompt handling ----------

    def register_prompt(self, observation: Observation) -> PromptData:
        with self._lock:
            self._prompt_seq += 1
            prompt_id = self._prompt_seq
            self._pending_action = None
            self._action_event.clear()

        phase = (observation.get("phase") or "").upper()
        if phase == "TURN":
            context = build_turn_context(observation)
            payload, actions = self._serialize_turn_prompt(prompt_id, context)
        else:
            context = build_reaction_context(observation)
            payload, actions = self._serialize_reaction_prompt(prompt_id, context)

        prompt = PromptData(prompt_id=prompt_id, payload=payload, actions=actions)
        with self._lock:
            self._current_prompt = prompt
            self._state["prompt"] = payload
            self._state_version += 1
        return prompt

    def _serialize_turn_prompt(
        self, prompt_id: int, context: TurnActionContext
    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        actions: Dict[str, Dict[str, Any]] = {}
        entries: List[Dict[str, Any]] = []

        discard_lookup: Dict[Tuple[Optional[int], str], TurnActionOption] = {
            (opt.tile, (opt.source or "hand")): opt for opt in context.discard_options
        }

        for idx, action in enumerate(context.legal_actions):
            action_id = f"act-{prompt_id}-{idx}"
            normalized = dict(action)
            actions[action_id] = normalized
            entry = self._build_turn_action_entry(action_id, normalized, discard_lookup)
            entries.append(entry)

        if (not context.declared_ting) and context.ting_candidates:
            for idx, option in enumerate(context.ting_candidates):
                action_id = f"ting-{prompt_id}-{idx}"
                action_dict = {"type": "TING", "tile": option.tile, "from": option.source}
                actions[action_id] = action_dict
                entry = {
                    "id": action_id,
                    "type": "TING",
                    "label": f"TING after discarding {tile_to_str(option.tile)}",
                    "tile": tile_to_str(option.tile),
                    "option": _label_for_turn_option(option),
                }
                entries.append(entry)

        payload = {
            "id": prompt_id,
            "phase": "TURN",
            "player": context.player,
            "discard_options": [_label_for_turn_option(opt) for opt in context.discard_options],
            "hand_tiles": [tile_to_str(t) for t in context.hand],
            "drawn": tile_to_str(context.drawn) if context.drawn is not None else None,
            "declared_ting": context.declared_ting,
            "current_waits": [_label_for_wait(wait) for wait in context.current_waits],
            "actions": entries,
        }
        return payload, actions

    def _build_turn_action_entry(
        self,
        action_id: str,
        action: Dict[str, Any],
        discard_lookup: Dict[Tuple[Optional[int], str], TurnActionOption],
    ) -> Dict[str, Any]:
        a_type = (action.get("type") or "").upper()
        entry: Dict[str, Any] = {
            "id": action_id,
            "type": a_type,
        }
        if a_type == "DISCARD":
            tile = action.get("tile")
            src = (action.get("from") or "hand")
            option = discard_lookup.get((tile, src))
            entry.update(
                {
                    "label": f"Discard {tile_to_str(tile)}",
                    "tile": tile_to_str(tile),
                    "source": src,
                    "option": _label_for_turn_option(option) if option else None,
                }
            )
        elif a_type in {"ANGANG", "KAKAN", "HU", "TING"}:
            tile = action.get("tile")
            entry.update(
                {
                    "label": f"{a_type} {tile_to_str(tile) if tile is not None else ''}".strip(),
                    "tile": tile_to_str(tile) if tile is not None else None,
                }
            )
        else:
            entry["label"] = a_type
        return entry

    def _serialize_reaction_prompt(
        self, prompt_id: int, context: ReactionContext
    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        actions: Dict[str, Dict[str, Any]] = {}
        entries: List[Dict[str, Any]] = []
        for idx, menu_option in enumerate(context.menu):
            action_id = f"react-{prompt_id}-{idx}"
            action_dict = dict(menu_option.action)
            actions[action_id] = action_dict
            entries.append(
                {
                    "id": action_id,
                    "type": (action_dict.get("type") or "").upper(),
                    "label": menu_option.label,
                    "priority": menu_option.priority,
                }
            )
        payload = {
            "id": prompt_id,
            "phase": "REACTION",
            "player": context.player,
            "last_discard": tile_to_str(context.last_discard_tile)
            if context.last_discard_tile is not None
            else None,
            "actions": entries,
        }
        return payload, actions

    def wait_for_action(self, prompt: PromptData, timeout: float = 0.5) -> Dict[str, Any]:
        while True:
            if self._action_event.wait(timeout):
                with self._lock:
                    if self._pending_action is not None and self._current_prompt == prompt:
                        action = dict(self._pending_action)
                        self._pending_action = None
                        self._current_prompt = None
                        self._state["prompt"] = None
                        self._state_version += 1
                        return action
                    if not self._session_active:
                        return {"type": "PASS"}
            else:
                with self._lock:
                    if not self._session_active:
                        return {"type": "PASS"}

    def submit_action(self, prompt_id: int, action_id: str) -> Dict[str, Any]:
        with self._lock:
            if not self._current_prompt or self._current_prompt.prompt_id != prompt_id:
                raise ValueError("Prompt expired")
            action = self._current_prompt.actions.get(action_id)
            if action is None:
                raise ValueError("Unknown action id")
            self._pending_action = dict(action)
            self._action_event.set()
            return dict(action)

    # ---------- Snapshots ----------

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            state_copy = copy.deepcopy(self._state)
            state_copy["history"] = list(self._history)
            state_copy["session"]["human_pid"] = self.human_pid
            if self._session_error:
                state_copy["session"]["error"] = self._session_error
            state_copy["version"] = self._state_version
        return state_copy


class WebTableAdapter(TableViewPort, HandSummaryPort):
    """Adapter wiring SessionService updates into the state manager."""

    def __init__(self, manager: WebSessionStateManager) -> None:
        self.manager = manager
        self._discard_counter = 0

    def on_session_start(self, *, env: Mahjong16Env, score_state: ScoreState) -> None:
        self.manager.reset_for_session()
        self.manager.update_table(
            env,
            discard_counter=self._discard_counter,
            last_action=None,
            score_state=score_state,
        )

    def on_hand_start(
        self,
        *,
        hand_index: int,
        jang_index: int,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self._discard_counter = 0
        self.manager.update_hand_progress(hand_index=hand_index, jang_index=jang_index)
        self.manager.update_table(
            env,
            discard_counter=self._discard_counter,
            last_action=None,
            score_state=score_state,
        )

    def on_step(
        self,
        *,
        event: StepEvent,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        last_action = None
        if event.info and "resolved_claim" in event.info:
            resolved = event.info["resolved_claim"]
            claim_type = (resolved.get("type") or "").upper()
            tile = resolved.get("tile")
            last_action = {
                "who": f"P{resolved.get('pid')}",
                "type": claim_type,
                "detail": tile_to_str(tile),
            }
            self.manager.append_history(
                {
                    "timestamp": _timestamp(),
                    "event": f"{last_action['who']} {claim_type}",
                    "detail": last_action.get("detail"),
                }
            )

        if event.action_type == "DISCARD" and event.discarded_tile is not None:
            self._discard_counter += 1
            last_action = {
                "who": f"P{event.acting_pid}",
                "type": "DISCARD",
                "detail": tile_to_str(event.discarded_tile),
            }
            self.manager.append_history(
                {
                    "timestamp": _timestamp(),
                    "event": f"P{event.acting_pid} DISCARD",
                    "detail": tile_to_str(event.discarded_tile),
                }
            )

        self.manager.update_table(
            env,
            discard_counter=self._discard_counter,
            last_action=last_action,
            score_state=score_state,
        )

    def on_hand_scored(
        self,
        *,
        hand_index: int,
        breakdown: Dict[int, List[Dict[str, Any]]],
        payments: List[int],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.manager.mark_hand_complete(
            summary={
                "hand_index": hand_index,
                "payments": payments,
                "breakdown": breakdown,
            }
        )
        self.manager.update_table(
            env,
            discard_counter=self._discard_counter,
            last_action=None,
            score_state=score_state,
        )

    def on_session_end(
        self,
        *,
        summaries: List[Dict[str, Any]],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.manager.finalize_session(summaries=summaries)

    # HandSummaryPort methods

    def on_hand_summary(self, summary: Dict[str, Any]) -> None:
        self.manager.mark_hand_complete(summary=summary)

    def finalize(self, summaries: List[Dict[str, Any]]) -> None:
        # Already handled in on_session_end
        pass


__all__ = [
    "WebSessionStateManager",
    "WebTableAdapter",
]
