from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..breakdown import ScoreAccumulator
from ..state import DerivedScoringState
from ..score_types import ScoringContext


ZHENG_FLOWER_MAP = {
    "E": {1, 5},
    "S": {2, 6},
    "W": {3, 7},
    "N": {4, 8},
}


@dataclass(frozen=True)
class FlowerSummary:
    """Aggregated counts derived from the winner's flower tiles."""

    zheng_hua: int
    hua_gang: int
    unique_count: int


def _flower_no(tile: int) -> int | None:
    from ...tiles import tile_to_str

    label = tile_to_str(tile)
    if label and label.startswith("F"):
        try:
            return int(label[1:])
        except Exception:
            return None
    return None


def _winner_wind(ctx: ScoringContext) -> str | None:
    try:
        seat_winds: Sequence[str] | None = getattr(ctx, "seat_winds", None)
        winner = getattr(ctx, "winner", None)
        if (
            seat_winds is not None
            and winner is not None
            and 0 <= winner < len(seat_winds)
        ):
            wind = seat_winds[winner]
            return wind.upper() if isinstance(wind, str) else None
    except Exception:
        return None
    return None


def _flower_numbers(flowers: Iterable[int]) -> list[int]:
    return [n for n in (_flower_no(tile) for tile in flowers) if isinstance(n, int)]


def _summarize_flowers(flowers: Sequence[int], seat_wind: str | None) -> FlowerSummary:
    numbers = _flower_numbers(flowers)
    unique = set(numbers)

    zheng_targets = ZHENG_FLOWER_MAP.get(seat_wind or "", set())
    zheng_hua = len(unique.intersection(zheng_targets)) if zheng_targets else 0

    has_seasons = {1, 2, 3, 4}.issubset(unique)
    has_gentlemen = {5, 6, 7, 8}.issubset(unique)
    hua_gang = int(has_seasons) + int(has_gentlemen)

    return FlowerSummary(
        zheng_hua=zheng_hua,
        hua_gang=hua_gang,
        unique_count=len(unique),
    )


def apply_flowers_rules(
    ctx: ScoringContext, state: DerivedScoringState, acc: ScoreAccumulator
) -> bool:
    """Apply flower related scoring, handling early flower wins."""

    flower_win_type = state.flower_win_type
    if flower_win_type:
        if flower_win_type == "ba_xian":
            acc.add("ba_xian")
        elif flower_win_type == "qi_qiang_yi":
            acc.add("qi_qiang_yi")
        else:
            acc.add(str(flower_win_type))
        return False

    flowers = state.flowers
    if not flowers or not getattr(ctx.rules, "enable_wind_flower_scoring", False):
        return True

    summary = _summarize_flowers(flowers, _winner_wind(ctx))

    if summary.zheng_hua:
        acc.add("zheng_hua", count=summary.zheng_hua)
    if summary.hua_gang:
        acc.add("hua_gang", count=summary.hua_gang)

    enable_flower_wins = getattr(ctx.rules, "enable_flower_wins", True)
    if summary.unique_count == 8:
        acc.add("ba_xian")
    elif summary.unique_count == 7 and not enable_flower_wins:
        acc.add("qi_qiang_yi")

    return True
