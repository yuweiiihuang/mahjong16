"""Transformations for exposing mahjong table state to the web client."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from domain import Mahjong16Env
from domain.tiles import tile_sort_key, tile_to_str


def _tile_payload(tile: Optional[int]) -> Optional[Dict[str, Any]]:
    if tile is None:
        return None
    return {
        "id": int(tile),
        "label": tile_to_str(tile),
    }


def _tiles_payload(tiles: Sequence[int]) -> List[Dict[str, Any]]:
    sorted_tiles = sorted([int(t) for t in tiles], key=tile_sort_key)
    return [payload for tile in sorted_tiles if (payload := _tile_payload(tile)) is not None]


def _meld_payload(meld: Any, *, mask_concealed: bool) -> Dict[str, Any]:
    if isinstance(meld, dict):
        meld_dict = dict(meld)
    else:
        to_dict = getattr(meld, "to_dict", None)
        if callable(to_dict):
            try:
                meld_dict = to_dict() or {}
            except Exception:  # pragma: no cover - defensive
                meld_dict = {}
        else:
            meld_dict = getattr(meld, "__dict__", {})
    tiles = meld_dict.get("tiles") or []
    if mask_concealed and bool(meld_dict.get("concealed")):
        payload_tiles: List[Dict[str, Any]] = []
    else:
        payload_tiles = _tiles_payload(tiles)
    return {
        "type": (meld_dict.get("type") or "").upper(),
        "tiles": payload_tiles,
        "concealed": bool(meld_dict.get("concealed", False)),
    }


def _player_field(player: Any, field: str, default: Any = None) -> Any:
    if isinstance(player, dict):
        return player.get(field, default)
    if player is None:
        return default
    return getattr(player, field, default)


def _player_payload(
    env: Mahjong16Env,
    pid: int,
    pov_pid: int,
    *,
    last_discard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    players = getattr(env, "players", None)
    player: Any = None
    if isinstance(players, Sequence) and not isinstance(players, (str, bytes)):
        if 0 <= pid < len(players):
            player = players[pid]
    get = lambda key, default=None: _player_field(player, key, default)
    is_self = pid == pov_pid

    seat_winds = getattr(env, "seat_winds", None)
    seat = seat_winds[pid] if isinstance(seat_winds, list) and pid < len(seat_winds) else None

    dealer_pid = getattr(env, "dealer_pid", None)
    declared_ting = bool(get("declared_ting", False))

    hand_tiles = _tiles_payload(get("hand") or []) if is_self else []
    drawn_tile = _tile_payload(get("drawn")) if is_self else None
    melds_iter = get("melds") or []
    melds = [_meld_payload(m, mask_concealed=not is_self) for m in melds_iter]
    flowers = _tiles_payload(get("flowers") or [])
    river_tiles = list(get("river") or [])

    highlight_index: Optional[int] = None
    if isinstance(last_discard, dict) and last_discard.get("pid") == pid:
        tile = last_discard.get("tile")
        if river_tiles and river_tiles[-1] == tile:
            highlight_index = len(river_tiles) - 1

    discards: List[Dict[str, Any]] = []
    for idx, tile in enumerate(river_tiles):
        payload = _tile_payload(tile)
        if payload is None:
            continue
        payload = dict(payload)
        payload["highlight"] = idx == highlight_index
        discards.append(payload)

    return {
        "pid": pid,
        "seat": seat,
        "is_self": is_self,
        "is_dealer": pid == dealer_pid,
        "declared_ting": declared_ting,
        "hand": hand_tiles,
        "drawn": drawn_tile,
        "melds": melds,
        "flowers": flowers,
        "discards": discards,
        "hand_size": len(get("hand") or []),
    }


def build_table_payload(
    env: Mahjong16Env,
    *,
    human_pid: int,
    discard_counter: Optional[int],
    last_action: Optional[Dict[str, Any]],
    score_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    last_discard = getattr(env, "last_discard", None)

    seat_winds = getattr(env, "seat_winds", None)
    order_pids: List[int] = []
    if isinstance(seat_winds, list):
        for w in ("E", "S", "W", "N"):
            if w in seat_winds:
                order_pids.append(seat_winds.index(w))
    if not order_pids:
        order_pids = list(range(env.rules.n_players))

    players_payload = [
        _player_payload(env, pid, human_pid, last_discard=last_discard) for pid in order_pids
    ]

    n_remaining = len(getattr(env, "wall", []))
    rules = getattr(env, "rules", None)
    dead_wall_reserved = None
    if rules is not None:
        mode = getattr(rules, "dead_wall_mode", "fixed")
        base = getattr(rules, "dead_wall_base", 16)
        n_gang = getattr(env, "n_gang", 0)
        dead_wall_reserved = base + (n_gang if mode == "gang_plus_one" else 0)

    totals = (score_state or {}).get("totals") or []
    deltas = (score_state or {}).get("deltas") or []

    return {
        "turn": getattr(env, "turn", None),
        "phase": getattr(env, "phase", None),
        "quan_feng": getattr(env, "quan_feng", None),
        "dealer_pid": getattr(env, "dealer_pid", None),
        "dealer_streak": getattr(env, "dealer_streak", None),
        "discard_counter": discard_counter,
        "last_action": last_action,
        "players": players_payload,
        "wall_remaining": n_remaining,
        "dead_wall_reserved": dead_wall_reserved,
        "seat_winds": seat_winds,
        "score_totals": totals,
        "score_deltas": deltas,
        "last_discard": last_discard,
    }


def static_asset_path(name: str) -> Path:
    return Path(__file__).with_suffix("").parent / "static" / name


__all__ = [
    "build_table_payload",
    "static_asset_path",
]
