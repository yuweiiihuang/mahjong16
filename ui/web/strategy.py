"""Strategy implementation that delegates human input to the web UI."""

from __future__ import annotations

from domain.gameplay import Action, Observation

from ui.web.bridge import WebSessionBridge
from ui.web.view_model import build_action_prompt


class WebHumanStrategy:
    """Wait for the web client to submit actions for the acting player."""

    def __init__(self, bridge: WebSessionBridge) -> None:
        self.bridge = bridge

    def choose(self, obs: Observation) -> Action:
        actions = obs.get("legal_actions", []) or []
        if not actions:
            return {"type": "PASS"}

        prompt, lookup = build_action_prompt(obs)
        self.bridge.prepare_pending(prompt, lookup)
        return self.bridge.wait_for_action()


__all__ = ["WebHumanStrategy"]
