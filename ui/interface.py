"""Utilities for routing human input between console and GUI implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.gameplay import Action, Observation


class HumanInputProvider(Protocol):
    """Protocol implemented by interactive UI layers capable of handling input."""

    def choose_turn_action(self, obs: Observation) -> Action:
        """Return an action for the player's own turn."""

    def choose_reaction_action(self, obs: Observation) -> Action:
        """Return an action while reacting to another player's discard."""


@dataclass
class _ConsoleProvider:
    """Default provider delegating to the Rich console prompts."""

    def choose_turn_action(self, obs: Observation) -> Action:
        from ui.console import prompt_turn_action

        return prompt_turn_action(obs)

    def choose_reaction_action(self, obs: Observation) -> Action:
        from ui.console import prompt_reaction_action

        return prompt_reaction_action(obs)


_active_provider: HumanInputProvider = _ConsoleProvider()


def get_active_provider() -> HumanInputProvider:
    """Return the currently active human input provider."""

    return _active_provider


def set_active_provider(provider: HumanInputProvider | None) -> None:
    """Update the global provider used by :class:`bots.policies.HumanStrategy`."""

    global _active_provider
    _active_provider = provider or _ConsoleProvider()


__all__ = ["HumanInputProvider", "get_active_provider", "set_active_provider"]

