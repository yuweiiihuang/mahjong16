"""Shared visible-state and variable legal-action encoding for BC and PPO."""
from __future__ import annotations

ENCODING_VERSION = 1
KINDS = ("DISCARD", "TING", "HU", "PASS", "CHI", "PONG", "GANG", "ANGANG", "KAKAN")
WINDS = ("E", "S", "W", "N")
SOURCES = ("TSUMO", "RON", "QIANG_GANG")
MELDS = ("CHI", "PONG", "GANG", "ANGANG", "KAKAN")


def _one_hot(value: object, values: tuple) -> list[float]:
    return [float(value == item) for item in values]


def _tiles(tiles: list, count: int = 34) -> list[float]:
    result = [0.0] * count
    for tile in tiles:
        if tile is not None:
            if type(tile) is not int or not 0 <= tile < count:
                raise ValueError("Invalid visible tile")
            result[tile] += 0.25
    return result


def encode(obs: dict) -> tuple[list[float], list[list[float]]]:
    """Encode only whitelisted visible fields; candidates retain their original order."""
    actions = obs["legal_actions"]
    if not actions:
        raise ValueError("Cannot encode a terminal or empty decision")
    winds = obs["seat_winds"]
    if len(winds) != 4 or set(winds) != set(WINDS):
        raise ValueError("Invalid seat winds")
    pid = obs["player"]
    origin = WINDS.index(winds[pid])
    seats = [winds.index(WINDS[(origin + offset) % 4]) for offset in range(4)]
    state = _tiles(obs["hand"])
    state += _tiles([] if obs["drawn"] is None else [obs["drawn"]])
    state += _tiles(obs["blocked_discards"])
    state += [float(obs["phase"] == "REACTION"), obs["n_remaining"] / 144.0]
    state += _one_hot(obs["quan_feng"], WINDS)
    state += _one_hot(winds[pid], WINDS)
    state += [obs["dealer_streak"] / 10.0]
    for seat in seats:
        player = obs["players"][seat]
        state += _tiles(obs["rivers"][seat])
        state += _tiles(player["flowers"], 42)[34:]
        state += [player["count"] / 17.0, float(player["has_drawn"]),
                  float(player["declared_ting"]), float(seat == obs["dealer"])]
        for kind in MELDS:
            melds = [m for m in player["melds"] if m["type"] == kind]
            state += _tiles([t for m in melds for t in m["tiles"]])
            state += [sum(t is None for m in melds for t in m["tiles"]) / 4.0]
    last = obs["last_discard"]
    state += _tiles([] if last is None else [last["tile"]])
    state += _one_hot(None if last is None else seats.index(last["pid"]), (0, 1, 2, 3))
    candidates = []
    for action in actions:
        if action["type"] not in KINDS:
            raise ValueError("Unknown action type")
        features = _one_hot(action["type"], KINDS)
        features += _tiles([] if "tile" not in action else [action["tile"]])
        features += _tiles(action.get("use", []))
        features += _one_hot(action.get("from"), ("hand", "drawn"))
        features += _one_hot(action.get("source"), SOURCES)
        candidates.append(features)
    return state, candidates
