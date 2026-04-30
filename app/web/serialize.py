from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from domain.tiles import N_TILES, is_flower, rank_of, suit_of

SEAT_BY_OFFSET = {
    0: "User",
    1: "Right",
    2: "Opponent",
    3: "Left",
}

CHINESE_DIGITS = {
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
}

HONOR_LABELS = {
    27: "東",
    28: "南",
    29: "西",
    30: "北",
    31: "中",
    32: "發",
    33: "白",
}

SUIT_SUFFIX = {
    0: "萬",
    1: "筒",
    2: "條",
}

WIND_LABELS = {
    "E": "東",
    "S": "南",
    "W": "西",
    "N": "北",
}

DEFAULT_NAMES = {
    "User": "You",
    "Right": "Moka",
    "Opponent": "Leaf",
    "Left": "Space",
}

SORT_GROUP_BY_SUIT = {
    0: 0,  # 萬
    2: 1,  # 條
    1: 2,  # 筒
    3: 3,  # 字
}


def tile_id_to_web_label(tile_id: int | None) -> str:
    """Convert an engine tile id into the web UI's Chinese label format."""

    if tile_id is None:
        return ""
    if is_flower(tile_id):
        return f"花{tile_id - N_TILES + 1}"
    if tile_id in HONOR_LABELS:
        return HONOR_LABELS[tile_id]
    rank = rank_of(tile_id)
    suit = suit_of(tile_id)
    if rank is None or suit not in SUIT_SUFFIX:
        return str(tile_id)
    return f"{CHINESE_DIGITS.get(rank, str(rank))}{SUIT_SUFFIX[suit]}"


def meld_to_labels(meld: Any) -> List[str]:
    tiles = []
    if isinstance(meld, dict):
        tiles = list(meld.get("tiles") or [])
    elif isinstance(meld, Sequence) and not isinstance(meld, (str, bytes)):
        tiles = list(meld)
    return [tile_id_to_web_label(tile) for tile in tiles]


def pid_to_relative_seat(seating_order: Sequence[int], pov_pid: int, pid: int) -> str:
    if pov_pid not in seating_order or pid not in seating_order:
        return "User" if pid == pov_pid else "Opponent"
    pov_index = seating_order.index(pov_pid)
    pid_index = seating_order.index(pid)
    offset = (pid_index - pov_index) % len(seating_order)
    return SEAT_BY_OFFSET.get(offset, "Opponent")


def build_seat_maps(seating_order: Sequence[int], pov_pid: int) -> Tuple[Dict[int, str], Dict[str, int]]:
    pid_to_seat = {pid: pid_to_relative_seat(list(seating_order), pov_pid, pid) for pid in seating_order}
    seat_to_pid = {seat: pid for pid, seat in pid_to_seat.items()}
    return pid_to_seat, seat_to_pid


def resolve_draw_pid(players: Sequence[Any]) -> Optional[int]:
    for player in players:
        drawn = getattr(player, "drawn", None)
        if drawn is not None:
            return getattr(player, "id", None)
    return None


def sort_hand_tiles_for_web(tile_ids: Sequence[int]) -> List[int]:
    def sort_key(tile_id: int) -> tuple[int, int, int]:
        if is_flower(tile_id):
            return (4, tile_id - N_TILES, tile_id)
        suit = suit_of(tile_id)
        rank = rank_of(tile_id)
        group = SORT_GROUP_BY_SUIT.get(suit, 5)
        if rank is not None:
            return (group, rank, tile_id)
        return (group, tile_id - 27, tile_id)

    return sorted(tile_ids, key=sort_key)


def serialize_table(
    *,
    env: Any,
    score_totals: Sequence[int],
    pov_pid: int,
    hand_index: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    seating_order = list(getattr(env, "seating_order", []) or list(range(len(getattr(env, "players", [])))))
    pid_to_seat, _seat_to_pid = build_seat_maps(seating_order, pov_pid)
    players = list(getattr(env, "players", []))

    draw_pid = resolve_draw_pid(players) if not getattr(env, "done", False) else None
    draw_seat = pid_to_seat.get(draw_pid) if isinstance(draw_pid, int) else None
    active_pid = getattr(env, "turn", None)
    if getattr(env, "phase", None) == "REACTION":
        active_pid = getattr(env, "reaction_queue", [None])[getattr(env, "reaction_idx", 0)] if getattr(env, "reaction_queue", None) else active_pid
    active_seat = pid_to_seat.get(active_pid) if isinstance(active_pid, int) else None

    table_players: List[Dict[str, Any]] = []
    seat_winds = list(getattr(env, "seat_winds", []) or [])
    for pid, player in enumerate(players):
        seat = pid_to_seat.get(pid, "Opponent")
        score = score_totals[pid] if pid < len(score_totals) else 0
        wind_raw = seat_winds[pid] if pid < len(seat_winds) else None
        table_players.append(
            {
                "id": f"p{pid}",
                "pid": pid,
                "name": DEFAULT_NAMES.get(seat, f"P{pid}"),
                "seat": seat,
                "score": score,
                "seatWind": WIND_LABELS.get(wind_raw, str(wind_raw) if wind_raw is not None else ""),
                "isDealer": pid == getattr(env, "dealer_pid", None),
            }
        )

    def player_tiles(pid: int) -> Tuple[List[str], List[int], Optional[str], Optional[int]]:
        if not (0 <= pid < len(players)):
            return [], [], None, None
        player = players[pid]
        hand_tiles = sort_hand_tiles_for_web(list(getattr(player, "hand", []) or []))
        drawn_tile = getattr(player, "drawn", None)
        hand_labels = [tile_id_to_web_label(tile) for tile in hand_tiles]
        return hand_labels, hand_tiles, tile_id_to_web_label(drawn_tile) if drawn_tile is not None else None, drawn_tile

    def concealed_labels_for(pid: int) -> List[str]:
        if not (0 <= pid < len(players)):
            return []
        player = players[pid]
        hand_size = len(getattr(player, "hand", []) or [])
        drawn_size = 1 if getattr(player, "drawn", None) is not None else 0
        return ["牌"] * (hand_size + drawn_size)

    seat_to_pid = {seat: pid for pid, seat in pid_to_seat.items()}
    user_pid = seat_to_pid.get("User", pov_pid)
    opp_pid = seat_to_pid.get("Opponent", pov_pid)
    left_pid = seat_to_pid.get("Left", pov_pid)
    right_pid = seat_to_pid.get("Right", pov_pid)

    self_hand, self_hand_ids, self_drawn, self_drawn_id = player_tiles(user_pid)
    opp_hand_labels = concealed_labels_for(opp_pid)
    left_hand_labels = concealed_labels_for(left_pid)
    right_hand_labels = concealed_labels_for(right_pid)

    def river_labels(pid: int) -> List[str]:
        if not (0 <= pid < len(players)):
            return []
        return [tile_id_to_web_label(tile) for tile in list(getattr(players[pid], "river", []) or [])]

    def flower_labels(pid: int) -> List[str]:
        if not (0 <= pid < len(players)):
            return []
        return [tile_id_to_web_label(tile) for tile in list(getattr(players[pid], "flowers", []) or [])]

    def meld_labels(pid: int) -> List[List[str]]:
        if not (0 <= pid < len(players)):
            return []
        return [meld_to_labels(meld) for meld in list(getattr(players[pid], "melds", []) or [])]

    table = {
        "anchorId": "engine-live",
        "activeSeat": active_seat,
        "drawSeat": draw_seat,
        "wind": WIND_LABELS.get(getattr(env, "quan_feng", None), str(getattr(env, "quan_feng", ""))),
        "round": hand_index,
        "timer": len(getattr(env, "wall", []) or []),
        "players": table_players,
        "selfHand": self_hand,
        "selfHandTileIds": self_hand_ids,
        "selfDrawn": self_drawn,
        "selfDrawnTileId": self_drawn_id,
        "selfDiscards": river_labels(user_pid),
        "selfFlowers": flower_labels(user_pid),
        "selfMelds": meld_labels(user_pid),
        "oppHand": opp_hand_labels,
        "oppDiscards": river_labels(opp_pid),
        "oppFlowers": flower_labels(opp_pid),
        "oppMelds": meld_labels(opp_pid),
        "leftHand": left_hand_labels,
        "leftDiscards": river_labels(left_pid),
        "leftFlowers": flower_labels(left_pid),
        "leftMelds": meld_labels(left_pid),
        "rightHand": right_hand_labels,
        "rightDiscards": river_labels(right_pid),
        "rightFlowers": flower_labels(right_pid),
        "rightMelds": meld_labels(right_pid),
    }
    meta = {
        "handIndex": hand_index,
        "jangIndex": getattr(getattr(env, "table_manager_state", None), "jang_count", None),
    }
    return table, meta
