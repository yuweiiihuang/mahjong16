"""Helpers for dumping Mahjong16 demo logs to timestamped CSV files."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from domain.tiles import tile_to_str

TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
DEFAULT_PLAYER_COUNT = 4
OPTIONAL_FIELD_ORDER = [
    "jang_index",
    "session_index",
    "session_hand_index",
    "global_hand_index",
    "session_seed",
]


def write_hand_log(hand_summaries: List[Dict[str, Any]], log_dir: Union[str, Path]) -> Optional[Path]:
    """Write per-hand summaries to a timestamped CSV in ``log_dir`` and return the file path."""
    if not hand_summaries:
        return None

    directory = Path(log_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)

    filename = f"{datetime.now().strftime(TIMESTAMP_FORMAT)}.csv"
    target = directory / filename

    max_players = _infer_player_count(hand_summaries)
    optional_fields = _detect_optional_fields(hand_summaries)
    fieldnames = _build_log_fieldnames(max_players, optional_fields)

    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in hand_summaries:
            writer.writerow(_hand_summary_to_row(summary, max_players, optional_fields))

    return target


def _infer_player_count(hand_summaries: List[Dict[str, Any]]) -> int:
    max_players = 0
    for summary in hand_summaries:
        payments = summary.get("payments") or []
        totals = summary.get("totals_after_hand") or []
        max_players = max(max_players, len(payments), len(totals))
    return max_players or DEFAULT_PLAYER_COUNT


def _detect_optional_fields(hand_summaries: List[Dict[str, Any]]) -> List[str]:
    present: List[str] = []
    for field in OPTIONAL_FIELD_ORDER:
        if any(field in summary for summary in hand_summaries):
            present.append(field)
    return present


def _build_log_fieldnames(max_players: int, optional_fields: Optional[List[str]] = None) -> List[str]:
    base_fields = [
        "hand_index",
        "result",
        "winner",
        "win_source",
        "ron_from",
        "dealer_pid",
        "win_tile",
        "remain_tiles",
        "winner_total_tai",
        "breakdown_tags",
        "winner_hand",
        "winner_melds",
        "winner_flowers",
        "quan_feng",
        "dealer_wind",
        "winner_wind",
        "base_points",
        "tai_points",
    ]
    if optional_fields:
        insert_pos = 1  # After hand_index
        for field in optional_fields:
            if field not in base_fields:
                base_fields.insert(insert_pos, field)
                insert_pos += 1
    delta_fields = [f"delta_p{i}" for i in range(max_players)]
    total_fields = [f"total_p{i}" for i in range(max_players)]
    return base_fields + delta_fields + total_fields


def _hand_summary_to_row(
    summary: Dict[str, Any],
    max_players: int,
    optional_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    row["hand_index"] = summary.get("hand_index")

    if optional_fields:
        for field in optional_fields:
            value = summary.get(field, "")
            row[field] = "" if value is None else value

    winner = summary.get("winner")
    win_source = (summary.get("win_source") or "").upper()

    if winner is None:
        row["result"] = summary.get("result", "DRAW")
        row["winner"] = ""
        row["win_source"] = ""
        row["ron_from"] = ""
        row["win_tile"] = ""
        row["winner_total_tai"] = 0
        row["winner_wind"] = ""
        row["winner_hand"] = ""
        row["winner_melds"] = ""
        row["winner_flowers"] = ""
        breakdown = []
    else:
        row["result"] = "WIN"
        row["winner"] = winner
        row["win_source"] = win_source
        row["ron_from"] = summary.get("ron_from") if win_source == "RON" else ""
        row["win_tile"] = _format_tile(summary.get("win_tile"))
        breakdown = summary.get("breakdown") or []
        row["winner_total_tai"] = sum(int(item.get("points", 0)) for item in breakdown)
        row["winner_wind"] = summary.get("winner_wind", "")
        row["winner_hand"] = _format_tiles(summary.get("hand"))
        row["winner_melds"] = _format_melds(summary.get("melds"))
        row["winner_flowers"] = _format_tiles(summary.get("flowers"))
    
    row["dealer_pid"] = summary.get("dealer_pid", "")
    row["quan_feng"] = summary.get("quan_feng", "")
    row["dealer_wind"] = summary.get("dealer_wind", "")
    row["base_points"] = summary.get("base_points", "")
    row["tai_points"] = summary.get("tai_points", "")
    row["breakdown_tags"] = "|".join(
        f"{item.get('key')}={int(item.get('points', 0))}" for item in breakdown
    )
    row["remain_tiles"] = summary.get("remain_tiles", "")

    payments = summary.get("payments") or []
    totals = summary.get("totals_after_hand") or []
    for idx in range(max_players):
        row[f"delta_p{idx}"] = int(payments[idx]) if idx < len(payments) else 0
    for idx in range(max_players):
        row[f"total_p{idx}"] = int(totals[idx]) if idx < len(totals) else 0

    return row


class HandLogWriter:
    """Incrementally append hand summaries to a single CSV log."""

    def __init__(
        self,
        log_dir: Union[str, Path],
        *,
        max_players: Optional[int] = None,
        optional_fields: Optional[List[str]] = None,
        filename: Optional[Union[str, Path]] = None,
    ) -> None:
        self.directory = Path(log_dir).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True)

        if filename is None:
            self._file_path: Optional[Path] = None
        else:
            candidate = Path(filename)
            if not candidate.is_absolute():
                candidate = self.directory / candidate
            self._file_path = candidate

        self._max_players = max_players
        self._optional_fields = list(optional_fields) if optional_fields is not None else OPTIONAL_FIELD_ORDER.copy()

        self._handle = None
        self._writer = None

    @property
    def path(self) -> Optional[Path]:
        """Return the file path once the log has been created."""
        return self._file_path

    def append(self, summary: Dict[str, Any]) -> None:
        """Append a single hand summary to the CSV, creating it if needed."""
        self._ensure_writer(summary)
        if self._writer is None:
            return
        row = _hand_summary_to_row(summary, self._max_players, self._optional_fields)
        self._writer.writerow(row)
        self._handle.flush()

    def append_many(self, summaries: List[Dict[str, Any]]) -> None:
        """Append multiple summaries to the CSV."""
        for summary in summaries:
            self.append(summary)

    def close(self) -> None:
        """Close the underlying file handle, if open."""
        if self._handle is not None:
            try:
                self._handle.flush()
            finally:
                self._handle.close()
        self._handle = None
        self._writer = None

    def _ensure_writer(self, summary: Dict[str, Any]) -> None:
        if self._writer is not None:
            return

        inferred_players = _infer_player_count([summary])
        if self._max_players is None:
            self._max_players = inferred_players or DEFAULT_PLAYER_COUNT
        else:
            self._max_players = max(self._max_players, inferred_players)

        if self._file_path is None:
            filename = f"{datetime.now().strftime(TIMESTAMP_FORMAT)}.csv"
            self._file_path = self.directory / filename
        else:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)

        self._handle = self._file_path.open("w", newline="", encoding="utf-8")
        fieldnames = _build_log_fieldnames(self._max_players, self._optional_fields)
        self._writer = csv.DictWriter(self._handle, fieldnames=fieldnames)
        self._writer.writeheader()


def _format_tile(tile_id: Any) -> str:
    if isinstance(tile_id, int):
        try:
            return tile_to_str(tile_id)
        except Exception:
            return str(tile_id)
    return ""


def _format_tiles(tiles: Any) -> str:
    if not isinstance(tiles, list):
        return ""
    parts = []
    for t in tiles:
        if isinstance(t, int):
            parts.append(_format_tile(t))
        else:
            parts.append(str(t))
    return " ".join(filter(None, parts))


def _format_melds(melds: Any) -> str:
    if not isinstance(melds, list):
        return ""
    formatted = []
    for m in melds:
        if isinstance(m, dict):
            mtype = (m.get("type") or "").upper()
            tiles = _format_tiles(m.get("tiles") or [])
            if tiles:
                formatted.append(f"{mtype}:{tiles}")
            else:
                formatted.append(mtype or "")
        else:
            formatted.append(str(m))
    return " | ".join(filter(None, formatted))
