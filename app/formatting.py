"""Lightweight CLI formatting helpers for tiles and melds.

This module is separate from the rich-based UI to keep ANSI-only formatting
concise for logs or prompts. Functions here avoid any rendering side effects.
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple
import re
from core.tiles import tile_to_str

ANSI_RESET = "\033[0m"
ANSI_RED   = "\033[31m"  # characters for 萬
ANSI_BLUE  = "\033[34m"  # characters for 筒
ANSI_GREEN = "\033[32m"  # characters for 條
ANSI_MAG   = "\033[35m"  # 字牌

ANSI_BY_SUIT = {
    "W": ANSI_RED,   # 萬
    "D": ANSI_BLUE,  # 筒
    "B": ANSI_GREEN, # 條
}

__all__ = [
    "fmt_tile",
    "render_melds",
    "colorize_text_tiles",
    "sort_tiles_for_display",
    "tile_sort_key",
]


def _colorize_label(s: str) -> str:
    """Apply ANSI color based on tile label suffix/prefix.

    Args:
      s: Tile label like '1W', '9D', or honor 'E'. May include trailing '*'.

    Returns:
      The colored label string (or original if not recognized).
    """
    if not s:
        return s
    
    core = s.rstrip("*")
    suffix = s[len(core):]
    if not core:
        return s

    ch0 = core[0]
    if ch0.isdigit() and len(core) >= 2:
        suit = core[-1]
        color = ANSI_BY_SUIT.get(suit)
        if color:
            return f"{color}{core}{ANSI_RESET}{suffix}"
    
    if len(core) == 1 and ch0 in "ESWNCFP":
        return f"{ANSI_MAG}{core}{ANSI_RESET}{suffix}"
    return core + suffix



def fmt_tile(t: int | None) -> str:
    """Format a tile id or None for display with color."""
    return "None" if t is None else _colorize_label(tile_to_str(t))


_TILE_TOKEN_RE = re.compile(r'(?<!\w)(?:[1-9][WDB]|[ESWNCFP])(?!\w)')


def _colorize_text_tiles(text: str) -> str:
    """Colorize inlined tile tokens in a plain string (regex-based).

    Args:
      text: Input string possibly containing tokens like '1W', '7D', 'E'.

    Returns:
      String with tokens wrapped in ANSI colors.
    """
    def _repl(m: re.Match) -> str:
        return _colorize_label(m.group(0))
    return _TILE_TOKEN_RE.sub(_repl, text)


def _suit_of(t: int) -> int:
    """Return suit index for tile id: 0=萬,1=筒,2=條,3=字。"""
    if 0 <= t <= 8: return 0
    if 9 <= t <= 17: return 1
    if 18 <= t <= 26: return 2
    return 3


def _rank_of(t: int) -> int:
    """Return rank (1..9) for suited tiles; 0 for honors."""
    if 0 <= t <= 8: return t - 0 + 1
    if 9 <= t <= 17: return t - 9 + 1
    if 18 <= t <= 26: return t - 18 + 1
    return 0


_HONOR_ORDER = {"E": 0, "S": 1, "W": 2, "N": 3, "C": 4, "F": 5, "P": 6}


def _honor_index(t: int) -> int:
    """Return a stable index for honor sorting (E,S,W,N,C,F,P)."""
    label = tile_to_str(t)
    key = label[0] if label else "?"
    return _HONOR_ORDER.get(key, 99)


def _tile_sort_key(t: int):
    """Sort key: suit, then rank/honor order, then label string."""
    s = _suit_of(t)
    return (s, _rank_of(t), tile_to_str(t)) if s < 3 else (s, _honor_index(t), tile_to_str(t))


def tile_sort_key(t: int):
    """sort key for tiles (by suit then rank)."""
    return _tile_sort_key(t)


def sort_tiles_for_display(tiles: List[int]) -> List[int]:
    """Return a new list of tiles sorted by suit then rank for display."""
    return sorted(tiles, key=_tile_sort_key)


def render_melds(melds: List[Dict[str, Any]]) -> str:
    """Render melds as simple bracketed strings with colored tiles.

    Args:
      melds: List of meld dicts: {"type": str, "tiles": List[int]}.

    Returns:
      A space-joined string like "[PONG 3W-3W-3W] [CHI 6D-7D-8D]" or "[]".
    """
    parts = []
    for m in melds or []:
        mtype = (m.get("type") or "").upper()
        tiles = list(m.get("tiles", []))
        tiles.sort()
        tiles_str = "-".join(_colorize_label(tile_to_str(t)) for t in tiles)
        if mtype in ("CHI", "PONG", "GANG"):
            parts.append(f"[{mtype} {tiles_str}]")
        else:
            parts.append(f"[{mtype or 'MELD'} {tiles_str}]")
    return " ".join(parts) if parts else "[]"

def colorize_text_tiles(text: str) -> str:
    """Colorize inlined tile tokens inside a string."""
    return _colorize_text_tiles(text)
