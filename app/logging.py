"""Helpers for dumping Mahjong16 demo logs to timestamped CSV files."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.tiles import tile_to_str

TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
DEFAULT_PLAYER_COUNT = 4


def write_hand_log(hand_summaries: List[Dict[str, Any]], log_dir: Union[str, Path]) -> Optional[Path]:
    """Write per-hand summaries to a timestamped CSV in ``log_dir`` and return the file path."""
    if not hand_summaries:
        return None

    directory = Path(log_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)

    filename = f"{datetime.now().strftime(TIMESTAMP_FORMAT)}.csv"
    target = directory / filename

    max_players = _infer_player_count(hand_summaries)
    fieldnames = _build_log_fieldnames(max_players)

    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in hand_summaries:
            writer.writerow(_hand_summary_to_row(summary, max_players))

    return target


def _infer_player_count(hand_summaries: List[Dict[str, Any]]) -> int:
    max_players = 0
    for summary in hand_summaries:
        payments = summary.get("payments") or []
        totals = summary.get("totals_after_hand") or []
        max_players = max(max_players, len(payments), len(totals))
    return max_players or DEFAULT_PLAYER_COUNT


def _build_log_fieldnames(max_players: int) -> List[str]:
    base_fields = [
        "hand_index",
        "result",
        "winner",
        "win_source",
        "ron_from",
        "win_tile",
        "winner_total_tai",
        "winner_hand",
        "winner_melds",
        "winner_flowers",
        "dealer_pid",
        "quan_feng",
        "dealer_wind",
        "winner_wind",
        "base_points",
        "tai_points",
        "breakdown_tags",
    ]
    delta_fields = [f"delta_p{i}" for i in range(max_players)]
    total_fields = [f"total_p{i}" for i in range(max_players)]
    return base_fields + delta_fields + total_fields


def _hand_summary_to_row(summary: Dict[str, Any], max_players: int) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    row["hand_index"] = summary.get("hand_index")

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

    payments = summary.get("payments") or []
    totals = summary.get("totals_after_hand") or []
    for idx in range(max_players):
        row[f"delta_p{idx}"] = int(payments[idx]) if idx < len(payments) else 0
    for idx in range(max_players):
        row[f"total_p{idx}"] = int(totals[idx]) if idx < len(totals) else 0

    return row


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
