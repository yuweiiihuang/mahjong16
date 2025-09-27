"""Rich rendering helpers shared by console UI components."""

from __future__ import annotations

from typing import Iterable, List, Optional

from rich.console import RenderableType
from rich.text import Text

from core.tiles import is_flower, tile_to_str


def style_for_tile(tile: int) -> str:
    """Return the Rich style used for a tile id."""

    label = tile_to_str(tile)
    if not label:
        return ""
    if is_flower(tile):
        return "yellow"
    if len(label) == 1:
        return "magenta"
    suit = label[-1]
    return {"W": "red", "D": "blue", "B": "green"}.get(suit, "")


def text_for_tile(tile: int, *, highlight: bool = False, dim: bool = False) -> Text:
    """Return a Rich Text snippet representing a tile."""

    label = tile_to_str(tile)
    txt = Text(label, style=style_for_tile(tile))
    if dim:
        txt.stylize("dim")
    if highlight:
        txt.stylize("reverse bold")
    return txt


def join_tiles(tiles: Iterable[int], *, highlight_tile: Optional[int] = None) -> Text:
    """Join tiles into a space-separated Rich Text sequence."""

    parts: List[Text] = []
    highlighted = False
    tiles_list = list(tiles)
    for idx, tile in enumerate(tiles_list):
        is_target = (
            not highlighted
            and highlight_tile is not None
            and tile == highlight_tile
        )
        parts.append(text_for_tile(tile, highlight=is_target))
        if is_target:
            highlighted = True
        if idx != len(tiles_list) - 1:
            parts.append(Text(" "))
    return Text.assemble(*parts)


def format_amount(amount: int | float) -> Text:
    """Return coloured Text for point deltas."""

    try:
        value = int(amount)
    except Exception:
        value = 0
    style = "green" if value > 0 else "red" if value < 0 else "dim"
    sign = "+" if value > 0 else ""
    return Text(f"{sign}{value}", style=style)


def render_melds(melds: List[dict], *, mask_concealed: bool = False) -> RenderableType:
    """Render melds as a Rich text sequence."""

    if not melds:
        return Text("[]", style="dim")
    chunks: List[Text] = []
    for meld in melds:
        mtype = (meld.get("type") or "").upper()
        tiles = sorted(list(meld.get("tiles") or []))
        pieces: List[Text] = [Text("[", style="dim"), Text(mtype or "MELD", style="bold")]
        if tiles:
            pieces.append(Text(" ", style="dim"))
            for idx, tile in enumerate(tiles):
                if mask_concealed and mtype == "ANGANG":
                    pieces.append(Text("##", style="dim"))
                else:
                    pieces.append(text_for_tile(tile))
                if idx != len(tiles) - 1:
                    pieces.append(Text("-", style="dim"))
        pieces.append(Text("]", style="dim"))
        chunks.append(Text.assemble(*pieces))
        chunks.append(Text(" "))
    if chunks:
        chunks.pop()
    return Text.assemble(*chunks)
