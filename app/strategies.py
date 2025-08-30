from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple, Protocol
from bots import GreedyBotStrategy
from core import Ruleset
from core.tiles import tile_to_str
from core.judge import waits_after_discard_17, waits_for_hand_16
from .formatting import (
    _colorize_label,
    _colorize_text_tiles,
    _colorize_tile,
    _tile_sort_key,
    _sort_tiles_for_display,
    fmt_tile,
    render_melds,
)

# Reaction priority: HU > GANG > PONG > CHI
PRIORITY = {"HU": 3, "GANG": 2, "PONG": 1, "CHI": 0}


class Strategy(Protocol):
    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]: ...


class AutoStrategy:
    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        acts = obs.get("legal_actions", []) or []
        phase = obs.get("phase")
        if phase == "REACTION":
            cand = [a for a in acts if (a.get("type") or "").upper() != "PASS"]
            if not cand:
                return {"type": "PASS"}
            cand.sort(key=lambda a: PRIORITY.get((a.get("type") or "").upper(), -1), reverse=True)
            return cand[0]
        hu = next((a for a in acts if (a.get("type") or "").upper() == "HU"), None)
        if hu is not None:
            return hu
        drawn_discard = next(
            (a for a in acts if (a.get("type") or "").upper() == "DISCARD" and a.get("from") == "drawn"),
            None
        )
        if drawn_discard is not None:
            return drawn_discard
        for a in acts:
            if (a.get("type") or "").upper() == "DISCARD":
                return a
        return {"type": "PASS"}


class HumanStrategy:
    def choose(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        acts = obs.get("legal_actions", []) or []
        player = obs.get("player")
        phase = obs.get("phase")
        if not acts:
            print("\n[auto] No legal actions → PASS")
            return {"type": "PASS"}

        if phase == "TURN":
            return self._choose_turn(obs, acts, player)
        else:
            return self._choose_reaction(obs, acts, player)

    def _choose_turn(self, obs: Dict[str, Any], acts: List[Dict[str, Any]], player: int) -> Dict[str, Any]:
        hand: List[int] = list(obs.get("hand") or [])
        drawn: Optional[int] = obs.get("drawn")
        hu_action = next((a for a in acts if (a.get("type") or "").upper() == "HU"), None)
        discards_all: List[Dict[str, Any]] = [a for a in acts if (a.get("type") or "").upper() == "DISCARD"]

        def key_disc(a: Dict[str, Any]) -> Tuple:
            t = a.get("tile")
            src = a.get("from", "hand")
            return (0 if src == "hand" else 1, *_tile_sort_key(t))

        discards_all.sort(key=key_disc)

        display_actions: List[Dict[str, Any]] = []
        display_labels: List[str] = []
        waits_list: List[List[int]] = []
        for a in discards_all:
            t = a.get("tile")
            lbl = tile_to_str(t)
            if a.get("from") == "drawn":
                lbl += "*"
            ws = waits_after_discard_17(hand, drawn, obs.get("melds") or [], t, a.get("from", "hand"), rules=Ruleset(include_flowers=False), exclude_exhausted=True)
            display_actions.append(a)
            display_labels.append(lbl)
            waits_list.append(ws)

        print(f"\n=== Your Turn | P{player} ===")
        sorted_hand_for_view = _sort_tiles_for_display(hand)
        print(f"Hand: {' '.join(_colorize_tile(t) for t in sorted_hand_for_view)}   Drawn: {fmt_tile(drawn)}")
        print(f"Melds: {render_melds(obs.get('melds') or [])}")
        if bool(obs.get("declared_ting", False)):
            waits_now = waits_for_hand_16(hand, obs.get("melds") or [], Ruleset(include_flowers=False), exclude_exhausted=True)
            if waits_now:
                def _visible_count_now(tile_id: int) -> int:
                    cnt = sum(1 for t in hand if t == tile_id)
                    for meld_list in (obs.get("melds_all") or []):
                        for m in (meld_list or []):
                            for x in (m.get("tiles") or []):
                                if x == tile_id:
                                    cnt += 1
                    for rv in (obs.get("rivers") or []):
                        for x in rv:
                            if x == tile_id:
                                cnt += 1
                    return cnt
                parts = []
                for w in sorted(waits_now, key=_tile_sort_key):
                    vis = _visible_count_now(w)
                    rem = max(0, 4 - min(4, vis))
                    parts.append(f"{tile_to_str(w)}({rem})")
                print(_colorize_text_tiles("TING: " + " ".join(parts)))

        def _after_discard(hand0: List[int], drawn0: Optional[int], tile0: int, src0: str) -> List[int]:
            h = list(hand0)
            if (src0 or "hand").lower() == "drawn":
                return h
            if tile0 in h:
                h.remove(tile0)
            if drawn0 is not None:
                h.append(drawn0)
            return h

        def _visible_count(tile_id: int, hand_after: List[int]) -> int:
            cnt = sum(1 for t in hand_after if t == tile_id)
            for meld_list in (obs.get("melds_all") or []):
                for m in (meld_list or []):
                    for t in (m.get("tiles") or []):
                        if t == tile_id:
                            cnt += 1
            for rv in (obs.get("rivers") or []):
                for t in rv:
                    if t == tile_id:
                        cnt += 1
            return cnt

        ting_candidates: List[Tuple[Dict[str, Any], List[int]]] = []
        for a, ws in zip(display_actions, waits_list):
            if ws:
                ting_candidates.append((a, ws))

        if (not bool(obs.get("declared_ting", False))) and ting_candidates:
            print("ACTIONS → " + ("[H] HU  " if hu_action is not None else "") + "[T] TING  [N] PASS")
            while True:
                raw0 = input("Declare TING? (T/N): ").strip().upper()
                if raw0 in ("H", "HU") and hu_action is not None:
                    return dict(hu_action)
                if raw0 in ("T", "TING", "Y", "YES"):
                    rows: List[str] = []
                    for i, (a, ws) in enumerate(ting_candidates):
                        t = a.get("tile")
                        src = a.get("from", "hand")
                        hand_after = _after_discard(hand, drawn, t, src)
                        waits_detail: List[str] = []
                        for w in sorted(ws, key=_tile_sort_key):
                            vis = _visible_count(w, hand_after)
                            rem = max(0, 4 - min(4, vis))
                            waits_detail.append(f"{tile_to_str(w)}({rem})")
                        label = f"[{i}] DISCARD {tile_to_str(t)}{'*' if src=='drawn' else ''} → TING: " + " ".join(waits_detail)
                        rows.append(_colorize_text_tiles(label))
                    print("TING OPTIONS →")
                    for r in rows:
                        print("  " + r)
                    while True:
                        sel = input("Pick TING option index: ").strip()
                        if sel.isdigit():
                            k = int(sel)
                            if 0 <= k < len(ting_candidates):
                                a, _ = ting_candidates[k]
                                return {"type": "TING", "tile": a.get("tile"), "from": a.get("from", "hand")}
                        print("索引超出範圍，請重新輸入。")
                if raw0 in ("N", "NO", "P", "PASS"):
                    break
                print("請輸入 T 或 N。")

        if hu_action is not None:
            print("ACTIONS → [H] HU")
        line = "  ".join(f"[{i}] {_colorize_label(lbl)}" for i, lbl in enumerate(display_labels))
        print(f"DISCARD → {line}")

        while True:
            raw = input("Discard index or tile: ").strip().upper()
            if hu_action is not None and raw in ("H", "HU"):
                return dict(hu_action)
            if raw.isdigit():
                idx = int(raw)
                if 0 <= idx < len(display_actions):
                    return dict(display_actions[idx])
                print("索引超出範圍，請重新輸入。")
                continue
            key = raw.rstrip("*")
            for a, lbl in zip(display_actions, display_labels):
                if lbl.rstrip("*").upper() == key:
                    return dict(a)
            print("無效輸入，請輸入索引或合法牌面（例如 7W）。")

    def _choose_reaction(self, obs: Dict[str, Any], acts: List[Dict[str, Any]], player: int) -> Dict[str, Any]:
        prio = {"HU": 0, "GANG": 1, "PONG": 2, "CHI": 3, "PASS": 9}
        ld = obs.get("last_discard") or {}
        ld_tile = ld.get("tile")

        def key_react(a: Dict[str, Any]):
            t = (a.get("type") or "").upper()
            if t == "CHI":
                use = a.get("use", [])
                s = [tile_to_str(x) for x in (use or [])]
                return (prio[t], s)
            return (prio.get(t, 99),)

        pass_action: Dict[str, Any] = next((a for a in acts if (a.get("type") or "").upper() == "PASS"), {"type": "PASS"})
        others_sorted = sorted([a for a in acts if (a.get("type") or "").upper() != "PASS"], key=key_react)

        def label_for(a: Dict[str, Any]) -> str:
            t = (a.get("type") or "").upper()
            if t == "PASS":
                return "PASS"
            if t == "CHI":
                use = a.get("use", [])
                if isinstance(use, list) and len(use) == 2:
                    u = f"{tile_to_str(use[0])}-{tile_to_str(use[1])}"
                    return f"CHI {u}  {tile_to_str(ld_tile) if ld_tile is not None else ''}".strip()
                return "CHI"
            if t in ("PONG", "GANG", "HU"):
                return f"{t} {tile_to_str(ld_tile) if ld_tile is not None else ''}".strip()
            return "PASS"

        menu_actions: List[Dict[str, Any]] = [pass_action] + others_sorted
        labels: List[str] = [label_for(a) for a in menu_actions]

        print(f"\n=== Your Reaction | P{player} → to {fmt_tile(ld_tile)} ===")
        print("  ".join(f"[{i}] {_colorize_text_tiles(lbl)}" for i, lbl in enumerate(labels)))

        while True:
            raw = input("Select action index: ").strip()
            if raw.isdigit():
                idx = int(raw)
                if 0 <= idx < len(menu_actions):
                    return dict(menu_actions[idx])
                print("索引超出範圍，請重新輸入。")
                continue
            print("請輸入數字索引。")


def build_strategies(n_players: int, human_pid: Optional[int], bot: str) -> List[Strategy]:
    strategies: List[Strategy] = []
    for pid in range(n_players):
        if human_pid is not None and pid == human_pid:
            strategies.append(HumanStrategy())
        else:
            if bot == "greedy":
                strategies.append(GreedyBotStrategy())
            elif bot == "human":
                strategies.append(HumanStrategy())
            else:
                strategies.append(AutoStrategy())
    return strategies

