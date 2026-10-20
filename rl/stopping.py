"""Finite, resumable validation patience with best-selection kept independent."""
from dataclasses import dataclass
import math


@dataclass
class Patience:
    """Minimize a measured objective; negate scores when larger is better.

    Tiny improvements can select a checkpoint without resetting stopping patience.
    Indices must increase, so replaying a validation receipt cannot count twice.
    """

    patience: int
    min_delta: float
    anchor: float
    best: float
    best_index: int = 0
    last_index: int = 0
    stale: int = 0

    def __post_init__(self) -> None:
        if (self.patience <= 0 or not math.isfinite(self.min_delta) or self.min_delta < 0
                or not math.isfinite(self.anchor) or not math.isfinite(self.best)
                or self.stale < 0 or not 0 <= self.best_index <= self.last_index):
            raise ValueError("Invalid validation stopping state")

    def observe(self, value: float, index: int) -> None:
        """Record one completed validation, rejecting nonfinite or repeated input."""
        if not math.isfinite(value) or index <= self.last_index:
            raise ValueError("Nonfinite or nonconsecutive validation measurement")
        if value < self.best:
            self.best, self.best_index = value, index
        if value < self.anchor - self.min_delta:
            self.anchor, self.stale = value, 0
        else:
            self.stale += 1
        self.last_index = index

    @property
    def stopped(self) -> bool:
        """Whether the configured number of unsuccessful checks was reached."""
        return self.stale >= self.patience
