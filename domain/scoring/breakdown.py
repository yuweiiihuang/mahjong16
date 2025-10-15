from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from .score_types import ScoringTable


@dataclass
class ScoreItem:
    """Single scoring entry used in the round breakdown."""

    key: str
    label: str
    base: int
    count: int
    points: int
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "base": self.base,
            "count": self.count,
            "points": self.points,
        }
        if self.meta:
            data["meta"] = dict(self.meta)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScoreItem":
        key = str(data.get("key", ""))
        label = str(data.get("label", key))
        base = _coerce_int(data.get("base", 0))
        count = _coerce_int(data.get("count", 0))
        points = _coerce_int(data.get("points", base * count))
        meta_raw = data.get("meta")
        meta = dict(meta_raw) if isinstance(meta_raw, dict) else None
        return cls(key=key, label=label, base=base, count=count, points=points, meta=meta)


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


class ScoreAccumulator:
    """Helper that normalises scoring items before serialising the breakdown."""

    def __init__(self, table: ScoringTable, player_id: int, n_players: int):
        self._table = table
        self._player_id = player_id
        self._n_players = max(0, int(n_players))
        self._items: List[ScoreItem] = []
        self._items_by_key: Dict[str, ScoreItem] = {}

    def add(
        self,
        key: str,
        base: int | None = None,
        count: int = 1,
        meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        base_value = _coerce_int(base if base is not None else self._table.get(key, 0))
        count_value = _coerce_int(count)
        if base_value == 0 or count_value == 0:
            return 0
        points = base_value * count_value

        item = self._items_by_key.get(key)
        if item is not None and item.base == base_value:
            item.count += count_value
            item.points += points
            if meta:
                if item.meta is None:
                    item.meta = dict(meta)
                else:
                    item.meta.update(meta)
        else:
            label = self._table.labels.get(key, key)
            new_item = ScoreItem(
                key=key,
                label=label,
                base=base_value,
                count=count_value,
                points=points,
                meta=dict(meta) if meta else None,
            )
            self._items.append(new_item)
            self._items_by_key[key] = new_item
        return points

    def extend(self, items: Iterable[ScoreItem | Dict[str, Any]]) -> None:
        for item in items:
            if isinstance(item, ScoreItem):
                score_item = item
            else:
                score_item = ScoreItem.from_dict(item)
            if score_item.base == 0 or score_item.count == 0:
                continue
            existing = self._items_by_key.get(score_item.key)
            if existing is not None and existing.base == score_item.base:
                existing.count += score_item.count
                existing.points += score_item.points
                if score_item.meta:
                    if existing.meta is None:
                        existing.meta = dict(score_item.meta)
                    else:
                        existing.meta.update(score_item.meta)
            else:
                meta = dict(score_item.meta) if score_item.meta else None
                label = score_item.label or self._table.labels.get(score_item.key, score_item.key)
                new_item = ScoreItem(
                    key=score_item.key,
                    label=label,
                    base=score_item.base,
                    count=score_item.count,
                    points=score_item.points,
                    meta=meta,
                )
                self._items.append(new_item)
                self._items_by_key[score_item.key] = new_item

    def total(self) -> int:
        return sum(item.points for item in self._items)

    def to_breakdown(self) -> Dict[int, List[Dict[str, Any]]]:
        breakdown: Dict[int, List[Dict[str, Any]]] = {
            pid: [] for pid in range(self._n_players)
        }
        if 0 <= self._player_id < self._n_players:
            breakdown[self._player_id] = [item.to_dict() for item in self._items]
        return breakdown
