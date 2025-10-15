"""Strategy proxy that delegates decisions to the web client."""

from __future__ import annotations

from typing import Any, Dict

from domain.gameplay import Action, Observation

from ui.web.manager import WebSessionStateManager


class WebHumanStrategy:
    """Strategy that waits for actions submitted via the web session manager."""

    def __init__(self, manager: WebSessionStateManager) -> None:
        self.manager = manager

    def choose(self, obs: Observation) -> Action:
        prompt = self.manager.register_prompt(obs)
        action: Dict[str, Any] = self.manager.wait_for_action(prompt)
        return action


__all__ = ["WebHumanStrategy"]
