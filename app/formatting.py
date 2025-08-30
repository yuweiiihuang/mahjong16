from __future__ import annotations
from typing import Dict, Any, List, Tuple
import re
from core.tiles import tile_to_str

# ANSI colors for CLI hints (console UI lives in ui.console)
ANSI_RESET = "\033[0m"
ANSI_RED   = "\033[31m"  # characters for Wan
ANSI_BLUE  = "\033[34m"  # characters for Tong
ANSI_GREEN = "\033[32m"  # characters for Tiao
ANSI_MAG   = "\033[35m"  # honors


def _colorize_label(s: str) -> str:
    if not s:
        return s
    if s.endswith("*"):
        core = s[:-1]
        return f"{_colorize_label(core)}*"
    ch0 = s[0]
    if ch0.isdigit() and len(s) >= 2:
        suit = s[-1]
        if suit == "W":
            return f"{ANSI_RED}{s}{ANSI_RESET}"
        if suit == "D":
            return f"{ANSI_BLUE}{s}{ANSI_RESET}"
        if suit == "B":
            return f"{ANSI_GREEN}{s}{ANSI_RESET}"
    if ch0 in "ESWNCFP" and len(s) == 1:
        return f"{ANSI_MAG}{s}{ANSI_RESET}"
    return s


def _colorize_tile(t: int) -> str:
    return _colorize_label(tile_to_str(t))


def fmt_tile(t: int | None) -> str:
    return "None" if t is None else _colorize_tile(t)


_TILE_TOKEN_RE = re.compile(r'(?<!\w)(?:[1-9][WDB]|[ESWNCFP])(?!\w)')


def _colorize_text_tiles(text: str) -> str:
    def _repl(m: re.Match) -> str:
        return _colorize_label(m.group(0))
    return _TILE_TOKEN_RE.sub(_repl, text)


def _suit_of(t: int) -> int:
    if 0 <= t <= 8: return 0
    if 9 <= t <= 17: return 1
    if 18 <= t <= 26: return 2
    return 3


def _rank_of(t: int) -> int:
    if 0 <= t <= 8: return t - 0 + 1
    if 9 <= t <= 17: return t - 9 + 1
    if 18 <= t <= 26: return t - 18 + 1
    return 0


_HONOR_ORDER = {"E": 0, "S": 1, "W": 2, "N": 3, "C": 4, "F": 5, "P": 6}


def _honor_index(t: int) -> int:
    label = tile_to_str(t)
    key = label[0] if label else "?"
    return _HONOR_ORDER.get(key, 99)


def _tile_sort_key(t: int):
    s = _suit_of(t)
    return (s, _rank_of(t), tile_to_str(t)) if s < 3 else (s, _honor_index(t), tile_to_str(t))


def _sort_tiles_for_display(tiles: List[int]) -> List[int]:
    return sorted(tiles, key=_tile_sort_key)


def render_melds(melds: List[Dict[str, Any]]) -> str:
    parts = []
    for m in melds or []:
        mtype = (m.get("type") or "").upper()
        tiles = list(m.get("tiles", []))
        tiles.sort()
        tiles_str = "-".join(_colorize_tile(t) for t in tiles)
        if mtype in ("CHI", "PONG", "GANG"):
            parts.append(f"[{mtype} {tiles_str}]")
        else:
            parts.append(f"[{mtype or 'MELD'} {tiles_str}]")
    return " ".join(parts) if parts else "[]"

