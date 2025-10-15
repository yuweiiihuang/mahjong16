"""Concrete adapters for session ports."""

from .rich_console import ConsoleUIAdapter
from .headless import HeadlessLogAdapter
from .web_frontend import WebFrontendAdapter

__all__ = ["ConsoleUIAdapter", "HeadlessLogAdapter", "WebFrontendAdapter"]
