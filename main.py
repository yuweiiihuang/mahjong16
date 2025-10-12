"""Thin shim that delegates the CLI to :mod:`mahjong16.interfaces.cli`."""

from __future__ import annotations

from mahjong16.interfaces.cli import main as cli_main


if __name__ == "__main__":
    cli_main()
