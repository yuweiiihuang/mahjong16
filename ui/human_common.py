"""Shared helpers for presenting human-facing mahjong actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from domain.analysis import simulate_after_discard, visible_count_after, visible_count_global
from domain.gameplay import Action, Observation
from domain.rules import Ruleset
from domain.rules.hands import waits_after_discard_17, waits_for_hand_16
from domain.tiles import tile_sort_key

DEFAULT_RULESET = Ruleset(include_flowers=False)


def _coerce_sequence(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


@dataclass
class WaitDetail:
    """Represents a single waiting tile and its remaining copies."""

    tile: int
    remaining: int


@dataclass
class TurnActionOption:
    """Information about a discard candidate during a player's turn."""

    action: Action
    tile: Optional[int]
    source: str
    waits: List[WaitDetail] = field(default_factory=list)

    @property
    def from_drawn(self) -> bool:
        return (self.source or "hand").lower() == "drawn"


@dataclass
class TurnActionContext:
    """Aggregated data for rendering a turn decision menu."""

    player: Optional[int]
    hand: List[int]
    drawn: Optional[int]
    melds: List[Dict[str, Any]]
    flowers: List[int]
    declared_ting: bool
    legal_actions: List[Action]
    hu_action: Optional[Action]
    angang_actions: List[Action]
    kakan_actions: List[Action]
    discard_options: List[TurnActionOption]
    ting_candidates: List[TurnActionOption]
    current_waits: List[WaitDetail]


@dataclass
class ReactionMenuOption:
    """Menu entry for a reaction choice (chi/pong/gang/hu/pass)."""

    action: Action
    label: str
    priority: int


@dataclass
class ReactionContext:
    """Aggregated data for rendering a reaction decision menu."""

    player: Optional[int]
    last_discard_tile: Optional[int]
    menu: List[ReactionMenuOption]


def _normalize_melds(values: Iterable[Any]) -> List[Dict[str, Any]]:
    melds: List[Dict[str, Any]] = []
    for meld in values:
        if isinstance(meld, dict):
            melds.append(dict(meld))
            continue
        to_dict = getattr(meld, "to_dict", None)
        if callable(to_dict):
            try:
                meld_dict = to_dict()
            except Exception:  # pragma: no cover - defensive
                meld_dict = {}
            if isinstance(meld_dict, dict):
                melds.append(meld_dict)
                continue
        attrs = getattr(meld, "__dict__", None)
        if isinstance(attrs, dict):
            melds.append(dict(attrs))
        else:
            melds.append({})
    return melds


def _build_wait_details(
    waits: Sequence[int],
    *,
    hand_after: Sequence[int],
    observation: Observation,
) -> List[WaitDetail]:
    details: List[WaitDetail] = []
    for tile in waits:
        visible = visible_count_after(tile, hand_after, observation)
        remaining = max(0, 4 - min(4, visible))
        details.append(WaitDetail(tile=tile, remaining=remaining))
    return details


def _current_ting_waits(obs: Observation, *, ruleset: Ruleset) -> List[WaitDetail]:
    waits_now = waits_for_hand_16(
        list(obs.get("hand") or []),
        _coerce_sequence(obs.get("melds")),
        ruleset,
        exclude_exhausted=True,
    )
    details: List[WaitDetail] = []
    for tile in waits_now:
        visible = visible_count_global(tile, obs)
        remaining = max(0, 4 - min(4, visible))
        details.append(WaitDetail(tile=tile, remaining=remaining))
    return sorted(details, key=lambda w: tile_sort_key(w.tile))


def build_turn_context(obs: Observation, *, ruleset: Optional[Ruleset] = None) -> TurnActionContext:
    """Build a structured representation for a player's turn observation."""

    acts: List[Action] = list(obs.get("legal_actions", []) or [])
    player = obs.get("player")
    hand = sorted(list(obs.get("hand") or []), key=tile_sort_key)
    drawn = obs.get("drawn")
    melds = _normalize_melds(_coerce_sequence(obs.get("melds")))
    flowers = sorted(list(obs.get("flowers") or []), key=tile_sort_key)
    declared_ting = bool(obs.get("declared_ting", False))

    rs = ruleset or DEFAULT_RULESET

    hu_action = next((a for a in acts if (a.get("type") or "").upper() == "HU"), None)
    angangs = [a for a in acts if (a.get("type") or "").upper() == "ANGANG"]
    kakans = [a for a in acts if (a.get("type") or "").upper() == "KAKAN"]

    discard_actions: List[Action] = [a for a in acts if (a.get("type") or "").upper() == "DISCARD"]

    def key_disc(a: Action) -> Tuple[Any, ...]:
        tile = a.get("tile")
        src = a.get("from", "hand")
        key = tile_sort_key(tile) if tile is not None else (99, 99)
        return (0 if src == "hand" else 1, *key)

    discard_actions.sort(key=key_disc)

    discard_options: List[TurnActionOption] = []
    ting_candidates: List[TurnActionOption] = []
    for action in discard_actions:
        tile = action.get("tile")
        src = action.get("from", "hand") or "hand"
        waits = waits_after_discard_17(
            list(obs.get("hand") or []),
            obs.get("drawn"),
            _coerce_sequence(obs.get("melds")),
            tile,
            src,
            rules=rs,
            exclude_exhausted=True,
        )
        hand_after = simulate_after_discard(
            list(obs.get("hand") or []),
            obs.get("drawn"),
            tile,
            src,
        )
        wait_details = _build_wait_details(waits, hand_after=hand_after, observation=obs)
        option = TurnActionOption(action=dict(action), tile=tile, source=src, waits=wait_details)
        discard_options.append(option)
        if wait_details:
            ting_candidates.append(option)

    current_waits: List[WaitDetail] = (
        _current_ting_waits(obs, ruleset=rs) if declared_ting else []
    )

    return TurnActionContext(
        player=player,
        hand=hand,
        drawn=drawn,
        melds=melds,
        flowers=flowers,
        declared_ting=declared_ting,
        legal_actions=acts,
        hu_action=dict(hu_action) if hu_action is not None else None,
        angang_actions=[dict(a) for a in angangs],
        kakan_actions=[dict(a) for a in kakans],
        discard_options=discard_options,
        ting_candidates=ting_candidates,
        current_waits=current_waits,
    )


def build_reaction_context(obs: Observation) -> ReactionContext:
    """Build menu representation for a reaction observation."""

    acts: List[Action] = list(obs.get("legal_actions", []) or [])
    player = obs.get("player")
    last_discard = obs.get("last_discard") or {}
    last_tile = last_discard.get("tile")

    priority_map = {"HU": 0, "GANG": 1, "PONG": 2, "CHI": 3, "PASS": 9}

    def reaction_priority(action: Action) -> Tuple[int, Any]:
        t = (action.get("type") or "").upper()
        if t == "CHI":
            use = action.get("use", [])
            return (priority_map[t], [tile_sort_key(x) for x in use])
        return (priority_map.get(t, 99),)

    pass_action = next(
        (a for a in acts if (a.get("type") or "").upper() == "PASS"),
        {"type": "PASS"},
    )
    others = [a for a in acts if (a.get("type") or "").upper() != "PASS"]
    others.sort(key=reaction_priority)

    def label_for(action: Action) -> str:
        t = (action.get("type") or "").upper()
        if t == "PASS":
            return "PASS"
        if t == "CHI":
            use = action.get("use", [])
            if isinstance(use, list) and len(use) == 2:
                return f"CHI {use[0]}-{use[1]} + {last_tile if last_tile is not None else '?'}"
            return "CHI"
        if t in {"PONG", "GANG", "HU"}:
            return f"{t} {last_tile if last_tile is not None else ''}".strip()
        return t

    menu: List[ReactionMenuOption] = [
        ReactionMenuOption(action=dict(pass_action), label=label_for(pass_action), priority=priority_map["PASS"])
    ]
    for action in others:
        menu.append(
            ReactionMenuOption(
                action=dict(action),
                label=label_for(action),
                priority=priority_map.get((action.get("type") or "").upper(), 99),
            )
        )

    return ReactionContext(player=player, last_discard_tile=last_tile, menu=menu)


__all__ = [
    "TurnActionContext",
    "TurnActionOption",
    "WaitDetail",
    "ReactionContext",
    "ReactionMenuOption",
    "build_turn_context",
    "build_reaction_context",
]
