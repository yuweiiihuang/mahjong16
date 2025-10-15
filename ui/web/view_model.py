"""Transform Mahjong16 environment state into web-friendly payloads."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from domain.analysis import simulate_after_discard, visible_count_after
from domain.rules import Ruleset
from domain.rules.hands import waits_after_discard_17
from domain.tiles import tile_sort_key, tile_to_str

_PROMPT_RULESET = Ruleset(include_flowers=False)


def _tile_label(tile: Optional[int]) -> Optional[str]:
    if tile is None:
        return None
    return tile_to_str(tile)


def _tiles_sequence(values: Iterable[int]) -> List[str]:
    return [tile_to_str(v) for v in sorted(list(values), key=tile_sort_key)]


def _format_tile(tile: Optional[int]) -> str:
    label = _tile_label(tile)
    if label is None:
        return "??"
    return label


def _players_for_env(env) -> Tuple[List[Any], int]:
    players = getattr(env, "players", None)
    if isinstance(players, list):
        return players, len(players)
    rules = getattr(env, "rules", None)
    max_slots = getattr(rules, "n_players", 0)
    return [], int(max_slots)


def _player_field(player: Any, field: str, default: Any = None) -> Any:
    if player is None:
        return default
    if isinstance(player, dict):
        return player.get(field, default)
    return getattr(player, field, default)


def _order_player_ids(env) -> List[int]:
    seat_winds = getattr(env, "seat_winds", None)
    order: List[int] = []
    try:
        if isinstance(seat_winds, list):
            for wind in ("E", "S", "W", "N"):
                if wind in seat_winds:
                    order.append(seat_winds.index(wind))
    except Exception:
        order = []
    if not order:
        order = list(range(env.rules.n_players))
    return order


def _seat_for_pid(env, pid: int) -> Optional[str]:
    seat_winds = getattr(env, "seat_winds", None)
    try:
        if isinstance(seat_winds, list) and 0 <= pid < len(seat_winds):
            seat = seat_winds[pid]
            if isinstance(seat, str):
                return seat.upper()
            if seat is not None:
                return str(seat)
    except Exception:
        return None
    return None


def _meld_payload(meld: Dict[str, Any], *, mask_concealed: bool) -> Dict[str, Any]:
    kind = (meld.get("type") or "").upper()
    tiles = list(meld.get("tiles") or [])
    tiles.sort(key=tile_sort_key)
    if mask_concealed and kind == "ANGANG":
        faceup = ["##" for _ in tiles]
    else:
        faceup = [tile_to_str(t) for t in tiles]
    return {
        "type": kind,
        "tiles": faceup,
        "concealed": bool(kind == "ANGANG"),
        "from_pid": meld.get("from_pid"),
    }


def build_table_state(
    env,
    *,
    pov_pid: int,
    discard_id: Optional[int] = None,
    last_action: Optional[Dict[str, str]] = None,
    score_state: Optional[Dict[str, List[int]]] = None,
) -> Dict[str, Any]:
    """Convert the live environment state into a serialisable snapshot."""

    players_payload: List[Dict[str, Any]] = []
    last_discard = getattr(env, "last_discard", None)
    players, _ = _players_for_env(env)
    for pid in _order_player_ids(env):
        player = players[pid] if 0 <= pid < len(players) else None
        is_self = pid == pov_pid
        hand = sorted(list(_player_field(player, "hand", [])), key=tile_sort_key)
        drawn = _player_field(player, "drawn")
        river = list(_player_field(player, "river", []))
        highlight_idx = None
        if (
            last_discard
            and last_discard.get("pid") == pid
            and river
            and river[-1] == last_discard.get("tile")
        ):
            highlight_idx = len(river) - 1
        melds_raw = list(_player_field(player, "melds", []))
        payload_melds = [
            _meld_payload(meld, mask_concealed=not is_self)
            for meld in melds_raw
        ]
        players_payload.append(
            {
                "pid": pid,
                "seat": _seat_for_pid(env, pid) or "?",
                "is_dealer": pid == getattr(env, "dealer_pid", None),
                "is_self": is_self,
                "declared_ting": bool(_player_field(player, "declared_ting", False)),
                "hand": _tiles_sequence(hand) if is_self else [],
                "hand_count": len(hand),
                "drawn": _tile_label(drawn) if is_self else None,
                "melds": payload_melds,
                "flowers": _tiles_sequence(_player_field(player, "flowers", [])),
                "river": [tile_to_str(t) for t in river],
                "river_highlight": highlight_idx,
            }
        )

    remaining = len(getattr(env, "wall", []))
    mode = getattr(env.rules, "dead_wall_mode", "fixed")
    base = getattr(env.rules, "dead_wall_base", 16)
    reserved = base + getattr(env, "n_gang", 0) if mode == "gang_plus_one" else base
    totals = list(score_state.get("totals", [])) if score_state else []
    deltas = list(score_state.get("deltas", [])) if score_state else []

    status = {
        "quan_feng": getattr(env, "quan_feng", None),
        "dealer_pid": getattr(env, "dealer_pid", None),
        "turn": getattr(env, "turn", None),
        "phase": getattr(env, "phase", None),
        "remaining": remaining,
        "dead_wall": reserved,
        "discard_id": discard_id,
        "totals": totals,
        "deltas": deltas,
    }
    if last_action:
        status["last_action"] = last_action

    return {
        "status": status,
        "players": players_payload,
    }


def build_reveal_payload(
    env,
    *,
    breakdown: Optional[Dict[int, List[Dict[str, Any]]]] = None,
    payments: Optional[List[int]] = None,
    totals: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Produce a reveal payload mirroring the Rich console output."""

    winner = getattr(env, "winner", None)
    win_src = getattr(env, "win_source", None)
    win_tile = getattr(env, "win_tile", None)
    turn_at_win = getattr(env, "turn_at_win", None)
    env_players, _ = _players_for_env(env)
    reveal_players: List[Dict[str, Any]] = []
    for pid in _order_player_ids(env):
        player = env_players[pid] if 0 <= pid < len(env_players) else None
        entry: Dict[str, Any] = {
            "pid": pid,
            "seat": _seat_for_pid(env, pid) or "?",
            "is_dealer": pid == getattr(env, "dealer_pid", None),
            "hand": _tiles_sequence(_player_field(player, "hand", [])),
            "melds": [
                _meld_payload(meld, mask_concealed=False)
                for meld in (_player_field(player, "melds", []))
            ],
            "flowers": _tiles_sequence(_player_field(player, "flowers", [])),
            "river": [tile_to_str(t) for t in (_player_field(player, "river", []))],
        }
        if pid == winner:
            entry["win_source"] = (win_src or "").upper()
            entry["win_tile"] = _tile_label(win_tile)
            if entry["win_source"] == "RON" and turn_at_win is not None:
                entry["ron_from"] = turn_at_win
            if breakdown and pid in breakdown:
                entry["breakdown"] = [dict(item) for item in breakdown.get(pid) or []]
        reveal_players.append(entry)

    return {
        "players": reveal_players,
        "payments": list(payments or []),
        "totals": list(totals or []),
        "base_points": getattr(env.rules, "base_points", None),
        "tai_points": getattr(env.rules, "tai_points", None),
        "winner": winner,
        "win_source": (win_src or "").upper() if win_src else None,
        "win_tile": _tile_label(win_tile),
    }


def build_action_prompt(obs) -> Tuple[Dict[str, any], Dict[str, Dict[str, any]]]:
    """Convert a human observation into an interactive action prompt."""

    actions = obs.get("legal_actions", []) or []
    options: List[Dict[str, any]] = []
    lookup: Dict[str, Dict[str, any]] = {}

    hand = sorted(list(obs.get("hand") or []), key=tile_sort_key)
    drawn = obs.get("drawn")
    melds = obs.get("melds") or []

    last_discard = obs.get("last_discard")
    discard_tile = last_discard.get("tile") if isinstance(last_discard, dict) else None

    for idx, action in enumerate(actions):
        action_type = (action.get("type") or "").upper()
        option_id = f"a{idx}"
        option: Dict[str, any] = {
            "id": option_id,
            "type": action_type,
        }
        tile = action.get("tile")
        if tile is None and discard_tile is not None and action_type in {"CHI", "PONG", "GANG", "HU"}:
            tile = discard_tile
        tile_label = _tile_label(tile)
        tile_display = _format_tile(tile)
        if tile_label is not None:
            option["tile"] = tile_label
        if action_type == "DISCARD":
            src = action.get("from", "hand")
            waits = waits_after_discard_17(
                hand,
                drawn,
                melds,
                tile,
                src,
                rules=_PROMPT_RULESET,
                exclude_exhausted=True,
            )
            hand_after = simulate_after_discard(hand, drawn, tile, src)
            option["source"] = src
            option["label"] = f"Discard {tile_display} ({src})"
            if waits:
                option["waits"] = [tile_to_str(w) for w in waits]
                remaining = []
                for wait_tile in waits:
                    vis = visible_count_after(wait_tile, hand_after, obs)
                    remaining.append(
                        {
                            "tile": tile_to_str(wait_tile),
                            "remaining": max(0, 4 - min(4, vis)),
                        }
                    )
                option["waits_remaining"] = remaining
        elif action_type == "TING":
            option["label"] = "Declare TING"
        elif action_type in {"HU", "PASS"}:
            option["label"] = action_type.title()
        elif action_type in {"ANGANG", "KAKAN"}:
            option["label"] = f"{action_type.title()} {tile_display}"
        elif action_type == "CHI":
            use_tiles = [_format_tile(t) for t in (action.get("use") or [])]
            chi_tiles = use_tiles + [tile_display]
            if chi_tiles:
                option["tiles"] = chi_tiles
                option["label"] = f"Chi {'-'.join(chi_tiles)}"
            else:
                option["label"] = "Chi"
        elif action_type in {"PONG", "GANG"}:
            option["label"] = f"{action_type.title()} {tile_display}"
        else:
            option["label"] = action_type.title()
        options.append(option)
        lookup[option_id] = dict(action)

    prompt: Dict[str, Any] = {
        "player": obs.get("player"),
        "phase": obs.get("phase"),
        "hand": _tiles_sequence(hand),
        "drawn": _tile_label(drawn),
        "flowers": _tiles_sequence(obs.get("flowers") or []),
        "actions": options,
        "n_remaining": obs.get("n_remaining"),
    }
    if isinstance(last_discard, dict):
        prompt["last_discard"] = {
            "pid": last_discard.get("pid"),
            "tile": _tile_label(last_discard.get("tile")),
            "source": last_discard.get("source"),
        }
    return prompt, lookup


__all__ = [
    "build_action_prompt",
    "build_reveal_payload",
    "build_table_state",
]
