"""Lightweight CLI formatting helpers for tiles and melds.

This module is separate from the rich-based UI to keep ANSI-only formatting
concise for logs or prompts. Functions here avoid any rendering side effects.
"""

from __future__ import annotations
from typing import Dict, Any, List
from core.tiles import tile_to_str, tile_sort_key

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
