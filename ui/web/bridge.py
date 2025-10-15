"""Synchronization primitives connecting the session loop with the web UI."""

from __future__ import annotations

import asyncio
import threading
from queue import Queue
from typing import Any, Dict, Iterable, List, Optional


class WebSessionBridge:
    """Thread-safe bridge between the backend session and web clients."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._subscribers: List[asyncio.Queue] = []
        self._base_state: Optional[Dict[str, Any]] = None
        self._reveal: Optional[Dict[str, Any]] = None
        self._pending_request: Optional[Dict[str, Any]] = None
        self._pending_serial: Optional[int] = None
        self._action_lookup: Dict[str, Dict[str, Any]] = {}
        self._hand_summaries: List[Dict[str, Any]] = []
        self._latest: Optional[Dict[str, Any]] = None
        self._next_serial = 1
        self.action_queue: "Queue[Dict[str, Any]]" = Queue()

    # ------------------------------------------------------------------
    # Event loop and subscription management
    # ------------------------------------------------------------------
    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the running event loop for async callbacks."""

        self._loop = loop

    async def updates(self) -> Iterable[Dict[str, Any]]:
        """Yield table state updates for a subscribed client."""

        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            if self._latest is not None:
                queue.put_nowait(dict(self._latest))
            self._subscribers.append(queue)
        try:
            while True:
                payload = await queue.get()
                if payload is None:
                    continue
                yield payload
        finally:
            with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)

    def latest_state(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._latest) if self._latest is not None else None

    # ------------------------------------------------------------------
    # State assembly helpers
    # ------------------------------------------------------------------
    def reset(self) -> None:
        with self._lock:
            self._base_state = None
            self._reveal = None
            self._pending_request = None
            self._pending_serial = None
            self._action_lookup = {}
            self._hand_summaries.clear()
            self._latest = None

    def update_base_state(self, state: Dict[str, Any]) -> None:
        with self._lock:
            self._base_state = dict(state)
            payload = self._compose_locked()
        self._broadcast(payload)

    def set_reveal(self, reveal: Optional[Dict[str, Any]]) -> None:
        with self._lock:
            self._reveal = dict(reveal) if reveal is not None else None
            payload = self._compose_locked()
        self._broadcast(payload)

    def append_summary(self, summary: Dict[str, Any]) -> None:
        with self._lock:
            self._hand_summaries.append(dict(summary))
            payload = self._compose_locked()
        self._broadcast(payload)

    def prepare_pending(self, request: Dict[str, Any], actions: Dict[str, Dict[str, Any]]) -> int:
        """Register a human action prompt and return its serial id."""

        with self._lock:
            serial = self._next_serial
            self._next_serial += 1
            self._pending_request = dict(request)
            self._pending_serial = serial
            self._action_lookup = {key: dict(value) for key, value in actions.items()}
            payload = self._compose_locked()
        self._broadcast(payload)
        return serial

    def clear_pending(self) -> None:
        with self._lock:
            self._pending_request = None
            self._pending_serial = None
            self._action_lookup = {}
            payload = self._compose_locked()
        self._broadcast(payload)

    def submit_action(self, *, serial: int, action_id: str) -> Dict[str, Any]:
        """Validate and enqueue a user action coming from the web client."""

        with self._lock:
            if self._pending_serial != serial:
                raise ValueError("stale action serial")
            if action_id not in self._action_lookup:
                raise KeyError("unknown action id")
            action = dict(self._action_lookup[action_id])
        self.action_queue.put(action)
        self.clear_pending()
        return action

    def wait_for_action(self) -> Dict[str, Any]:
        """Block until the human client submits an action."""

        return self.action_queue.get()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _compose_locked(self) -> Optional[Dict[str, Any]]:
        if self._base_state is None:
            self._latest = None
            return None
        state = dict(self._base_state)
        if self._reveal is not None:
            state["reveal"] = dict(self._reveal)
        if self._hand_summaries:
            state["hand_summaries"] = [dict(item) for item in self._hand_summaries]
        if self._pending_request is not None and self._pending_serial is not None:
            pending = dict(self._pending_request)
            pending["serial"] = self._pending_serial
            state["pending_request"] = pending
        self._latest = state
        return state

    def _broadcast(self, payload: Optional[Dict[str, Any]]) -> None:
        with self._lock:
            self._latest = dict(payload) if payload is not None else None
            queues = list(self._subscribers)
            message = self._latest
        if self._loop is None:
            return

        def _dispatch() -> None:
            for queue in queues:
                queue.put_nowait(message)

        self._loop.call_soon_threadsafe(_dispatch)


__all__ = ["WebSessionBridge"]
