"""State dataclasses for Mahjong environment."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class PlayerState:
    """Mutable state tracked for each seated player in the table."""

    id: int
    hand: List[int] = field(default_factory=list)
    drawn: Optional[int] = None
    flowers: List[int] = field(default_factory=list)
    melds: List[Any] = field(default_factory=list)
    river: List[int] = field(default_factory=list)
    score: int = 0
    declared_ting: bool = False
    ting_declared_at: Optional[int] = None
    ting_declared_open_melds: Optional[int] = None

    def as_dict(self) -> dict[str, Any]:
        """Return a shallow dictionary snapshot of the player state."""

        return {
            "id": self.id,
            "hand": list(self.hand),
            "drawn": self.drawn,
            "flowers": list(self.flowers),
            "melds": list(self.melds),
            "river": list(self.river),
            "score": self.score,
            "declared_ting": self.declared_ting,
            "ting_declared_at": self.ting_declared_at,
            "ting_declared_open_melds": self.ting_declared_open_melds,
        }
