"""Shared typed structures for mahjong16 core and UI layers.

These TypedDict definitions describe the observation/action schemas used by the
environment and reused by UI and strategy modules. Centralising the schema
avoids each module defining its own loosely-typed dict contracts.
"""

from __future__ import annotations

from typing import List, Literal, Optional, TypedDict


class MeldPublic(TypedDict, total=False):
    """Public description of a meld shown on the table."""

    type: str
    tiles: List[int]
    from_pid: int
    taken: int
    source: str


class DiscardPublic(TypedDict, total=False):
    """Public information about the latest discard."""

    pid: int
    tile: int
    source: str


Action = TypedDict(
    "Action",
    {
        "type": Literal[
            "DISCARD",
            "TING",
            "HU",
            "PASS",
            "CHI",
            "PONG",
            "GANG",
            "ANGANG",
            "KAKAN",
        ],
        "tile": int,
        "from": str,
        "use": List[int],
        "waits": List[int],
        "source": str,
    },
    total=False,
)


class Observation(TypedDict, total=False):
    """Observation returned by :class:`Mahjong16Env` for the acting player."""

    player: int
    phase: Literal["TURN", "REACTION"]
    hand: List[int]
    drawn: Optional[int]
    flowers: List[int]
    melds: List[MeldPublic]
    declared_ting: bool
    melds_all: List[List[MeldPublic]]
    rivers: List[List[int]]
    n_remaining: int
    last_discard: Optional[DiscardPublic]
    legal_actions: List[Action]

