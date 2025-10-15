"""Shared helpers for session adapters."""

from __future__ import annotations

from typing import Any, Dict, Optional

from domain.tiles import tile_to_str


def summarize_resolved_claim(info: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """Return a concise description of a resolved reaction claim."""

    if not info or "resolved_claim" not in info:
        return None
    resolved = info["resolved_claim"]
    claim_type = (resolved.get("type") or "").upper()
    pid = resolved.get("pid")
    tile = resolved.get("tile")
    detail = ""
    if claim_type == "CHI":
        use = resolved.get("use", [])
        if isinstance(use, list) and len(use) == 2:
            detail = f"{tile_to_str(use[0])}-{tile_to_str(use[1])} + {tile_to_str(tile)}"
    elif claim_type in {"PONG", "GANG", "HU"}:
        detail = tile_to_str(tile) or ""
    return {"who": f"P{pid}", "type": claim_type, "detail": detail}


__all__ = ["summarize_resolved_claim"]
