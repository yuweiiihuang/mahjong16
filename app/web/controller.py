from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from app.runtime import _build_session_dependencies
from domain.scoring.engine import compute_payments, score_with_breakdown
from domain.scoring.score_types import ScoringContext

from .serialize import WIND_LABELS, pid_to_relative_seat, serialize_table


class SessionError(RuntimeError):
    """Base class for session API failures."""


class SessionNotFoundError(SessionError):
    """Raised when a session id is unknown."""


class InvalidSessionStateError(SessionError):
    """Raised when an action is not valid for the current controller state."""


class InvalidActionError(SessionError):
    """Raised when a submitted action does not match current legal actions."""


@dataclass
class HandResult:
    payments: List[int]
    totals_after_hand: List[int]
    winner_pid: Optional[int]
    winner_seat: Optional[str]
    win_source: Optional[str]
    winner_breakdown: List[Dict[str, Any]]


def _canonical_action(action: Dict[str, Any]) -> str:
    return json.dumps(action, sort_keys=True, separators=(",", ":"))


class WebSessionController:
    """Step-driven single-table controller for the local web UI."""

    def __init__(
        self,
        *,
        seed: Optional[int] = None,
        human_pid: int = 0,
        bot: str = "auto",
        hands: int = -1,
        jangs: int = 0,
        start_points: int = 1000,
    ) -> None:
        env, table_manager, strategies, scoring_table = _build_session_dependencies(seed, None, bot)
        self.env = env
        self.table_manager = table_manager
        self.strategies = list(strategies)
        self.scoring_assets = scoring_table
        self.n_players = env.rules.n_players
        self.human_pid = human_pid
        self.hands = hands
        self.target_jangs = self._normalize_jangs(jangs)
        self.play_until_negative = hands == -1 and self.target_jangs is None
        self.max_hands = None if self.play_until_negative or self.target_jangs is not None else hands
        self.start_points = self._normalize_start_points(start_points)
        self.score_totals = [self.start_points for _ in range(self.n_players)]
        self.hand_delta = [0 for _ in range(self.n_players)]
        self.table_manager.initialize(self.n_players)
        self.current_observation: Optional[Dict[str, Any]] = None
        self.hand_index = 0
        self.status = "awaiting_action"
        self.result: Optional[HandResult] = None
        self.finished = False
        self._lock = threading.RLock()
        setattr(self.env, "table_manager_state", self.table_manager.state)
        self._advance_until_stop()

    def snapshot(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            table, meta = self._serialize_table()
            return {
                "sessionId": session_id,
                "status": self.status,
                "table": table,
                "legalActions": list(self.current_observation.get("legal_actions", [])) if self.current_observation else [],
                "result": self._serialize_result(),
                "meta": {
                    **meta,
                    "dealerPid": getattr(self.env, "dealer_pid", None),
                    "dealerSeat": self._pid_to_seat(getattr(self.env, "dealer_pid", None)),
                    "quanFeng": WIND_LABELS.get(getattr(self.env, "quan_feng", None), getattr(self.env, "quan_feng", None)),
                    "phase": (
                        self.current_observation.get("phase")
                        if self.current_observation
                        else getattr(self.env, "phase", None)
                    ),
                    "activeSeat": table.get("activeSeat"),
                    "drawSeat": table.get("drawSeat"),
                    "humanPid": self.human_pid,
                },
            }

    def submit_action(self, action: Dict[str, Any]) -> None:
        with self._lock:
            if self.status != "awaiting_action":
                raise InvalidSessionStateError("session is not waiting for a player action")
            current = self.current_observation or {}
            if current.get("player") != self.human_pid:
                raise InvalidSessionStateError("human seat is not active")
            legal_actions = list(current.get("legal_actions") or [])
            submitted = self._strip_action(action)
            allowed = {_canonical_action(self._strip_action(candidate)) for candidate in legal_actions}
            if _canonical_action(submitted) not in allowed:
                raise InvalidActionError("submitted action is not legal in the current state")
            self.current_observation, _reward, done, _info = self.env.step(submitted)
            if done:
                self._finish_current_hand()
                return
            self._advance_until_stop()

    def continue_after_result(self) -> None:
        with self._lock:
            if self.status not in {"hand_result", "finished"}:
                raise InvalidSessionStateError("session is not waiting at a hand boundary")
            if self.status == "finished":
                raise InvalidSessionStateError("session is already finished")
            self.result = None
            self.current_observation = None
            self.status = "awaiting_action"
            self._advance_until_stop()

    def _advance_until_stop(self) -> None:
        while True:
            if self.finished:
                self.status = "finished"
                return
            if self.result is not None:
                self.status = "hand_result"
                return
            if self.current_observation is None:
                if not self._can_start_next_hand():
                    self.finished = True
                    self.status = "finished"
                    return
                self.hand_index += 1
                self.current_observation = self.table_manager.start_hand(self.env)
                self.hand_delta = [0 for _ in range(self.n_players)]
                setattr(self.env, "table_manager_state", self.table_manager.state)
                if getattr(self.env, "done", False):
                    self._finish_current_hand()
                    continue

            observation = self._resolve_actions(self.current_observation)
            if observation is None:
                self._finish_current_hand()
                continue
            self.current_observation = observation
            acting_pid = observation.get("player")
            if observation.get("legal_actions") and acting_pid == self.human_pid:
                self.status = "awaiting_action"
                return
            if not observation.get("legal_actions"):
                raise InvalidSessionStateError(
                    f"no legal actions available for player {acting_pid} in phase {observation.get('phase')}"
                )
            action = self.strategies[acting_pid].choose(observation)
            self.current_observation, _reward, done, _info = self.env.step(action)
            if done:
                self._finish_current_hand()
                return

    def _resolve_actions(self, observation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        actions = list(observation.get("legal_actions") or [])
        if actions:
            return observation
        refreshed = self.env.legal_actions(pid=None if observation.get("phase") == "TURN" else observation.get("player"))
        if refreshed:
            updated = dict(observation)
            updated["legal_actions"] = refreshed
            return updated
        if getattr(self.env, "done", False):
            return None
        return observation

    def _finish_current_hand(self) -> None:
        ctx = ScoringContext.from_env(self.env, self.scoring_assets)
        rewards, breakdown = score_with_breakdown(ctx)
        payments_raw, _ = compute_payments(
            ctx,
            getattr(self.env.rules, "base_points", 100),
            getattr(self.env.rules, "tai_points", 20),
            rewards=rewards,
            breakdown=breakdown,
        )

        payments = [0 for _ in range(self.n_players)]
        for pid in range(self.n_players):
            raw = payments_raw[pid] if pid < len(payments_raw) else 0
            payments[pid] = int(raw) if raw is not None else 0
            self.score_totals[pid] += payments[pid]
            self.hand_delta[pid] = payments[pid]

        winner_pid = getattr(self.env, "winner", None)
        winner_seat = self._pid_to_seat(winner_pid) if winner_pid is not None else None
        self.result = HandResult(
            payments=list(payments),
            totals_after_hand=list(self.score_totals),
            winner_pid=winner_pid,
            winner_seat=winner_seat,
            win_source=getattr(self.env, "win_source", None),
            winner_breakdown=list(breakdown.get(winner_pid, [])) if winner_pid is not None else [],
        )

        self.table_manager.finish_hand(self.env)
        setattr(self.env, "table_manager_state", self.table_manager.state)
        self.current_observation = None

        if self.target_jangs is not None:
            jang_count = getattr(self.table_manager.state, "jang_count", 0)
            if jang_count >= self.target_jangs:
                self.finished = True
        if self.play_until_negative and any(total < 0 for total in self.score_totals):
            self.finished = True
        if self.finished:
            self.status = "finished"
        else:
            self.status = "hand_result"

    def _serialize_table(self) -> tuple[Dict[str, Any], Dict[str, Any]]:
        table, meta = serialize_table(
            env=self.env,
            score_totals=self.score_totals,
            pov_pid=self.human_pid,
            hand_index=self.hand_index,
        )
        meta["jangIndex"] = getattr(self.table_manager.state, "jang_count", 0) + 1
        return table, meta

    def _serialize_result(self) -> Optional[Dict[str, Any]]:
        if self.result is None:
            return None
        return {
            "payments": list(self.result.payments),
            "totalsAfterHand": list(self.result.totals_after_hand),
            "winnerPid": self.result.winner_pid,
            "winnerSeat": self.result.winner_seat,
            "winSource": self.result.win_source,
            "winnerBreakdown": list(self.result.winner_breakdown),
        }

    def _pid_to_seat(self, pid: Optional[int]) -> Optional[str]:
        if pid is None:
            return None
        seating_order = list(getattr(self.env, "seating_order", []) or list(range(self.n_players)))
        return pid_to_relative_seat(seating_order, self.human_pid, pid)

    def _can_start_next_hand(self) -> bool:
        return self.max_hands is None or self.hand_index < self.max_hands

    @staticmethod
    def _strip_action(action: Dict[str, Any]) -> Dict[str, Any]:
        allowed_keys = {"type", "tile", "from", "use", "waits", "source"}
        return {key: value for key, value in action.items() if key in allowed_keys}

    @staticmethod
    def _normalize_start_points(start_points: int) -> int:
        try:
            value = int(start_points)
        except Exception:
            value = 1000
        return value if value > 0 else 1

    @staticmethod
    def _normalize_jangs(jangs: Optional[int]) -> Optional[int]:
        if jangs is None:
            return None
        try:
            value = int(jangs)
        except Exception:
            return None
        return value if value > 0 else None


class SessionRegistry:
    """In-memory registry of web sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, WebSessionController] = {}
        self._lock = threading.Lock()

    def create(self) -> tuple[str, WebSessionController]:
        session_id = uuid.uuid4().hex
        controller = WebSessionController()
        with self._lock:
            self._sessions[session_id] = controller
        return session_id, controller

    def get(self, session_id: str) -> WebSessionController:
        with self._lock:
            controller = self._sessions.get(session_id)
        if controller is None:
            raise SessionNotFoundError(f"unknown session id: {session_id}")
        return controller
