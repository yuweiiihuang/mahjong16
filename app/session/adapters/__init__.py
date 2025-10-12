"""Concrete adapters for session ports."""

from .rich_console import ConsoleUIAdapter
from .headless import HeadlessLogAdapter

__all__ = ["ConsoleUIAdapter", "HeadlessLogAdapter"]
