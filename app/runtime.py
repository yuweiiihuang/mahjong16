from __future__ import annotations
from typing import Dict, Any, Optional
from core import Mahjong16Env, Ruleset
from core.tiles import tile_to_str
from core.judge import score_with_breakdown
from ui.console import render_public_view, render_reveal
from .formatting import fmt_tile, _colorize_tile
from .strategies import build_strategies


class Formatter:
    @staticmethod
    def print_action_line(act: Dict[str, Any], obs: Dict[str, Any]) -> None:
        t = (act.get("type") or "").upper()
        pid = obs.get("player")
        if t == "HU":
            src = act.get("source", "unknown")
            if obs.get("phase") == "REACTION":
                ld = obs.get("last_discard") or {}
                tt = ld.get("tile")
                print(f"P{pid} HU (source={src}, tile={fmt_tile(tt)})")
            else:
                print(f"P{pid} HU (source={src}, tile={fmt_tile(obs.get('drawn'))})")
        elif t == "TING":
            src = act.get("from", "hand")
            tt = act.get("tile")
            print(f"P{pid} TING -> DISCARD {fmt_tile(tt)} from {src}")
        elif t in ("GANG", "PONG"):
            ld = obs.get("last_discard") or {}
            tt = ld.get("tile")
            print(f"P{pid} {t} {fmt_tile(tt)}")
        elif t == "CHI":
            use = act.get("use", [])
            ld = obs.get("last_discard") or {}
            tt = ld.get("tile")
            if isinstance(use, list) and len(use) == 2:
                print(f"P{pid} CHI ({_colorize_tile(use[0])},{_colorize_tile(use[1])}) + {fmt_tile(tt)}")
            else:
                print(f"P{pid} CHI {fmt_tile(tt)}")


def summarize_resolved_claim(info: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not info or "resolved_claim" not in info:
        return None
    rc = info["resolved_claim"]
    t = (rc.get("type") or "").upper()
    pid = rc.get("pid")
    tile = rc.get("tile")
    detail = ""
    if t == "CHI":
        use = rc.get("use", [])
        if isinstance(use, list) and len(use) == 2:
            detail = f"{tile_to_str(use[0])}-{tile_to_str(use[1])} + {tile_to_str(tile)}"
    elif t in ("PONG", "GANG", "HU"):
        detail = tile_to_str(tile) or ""
    return {"who": f"P{pid}", "type": t, "detail": detail}


def update_ui(env: Mahjong16Env, human_pid: Optional[int], discard_id: int, last_action: Optional[Dict[str, Any]] = None) -> None:
    pov = (human_pid if human_pid is not None else 0)
    render_public_view(env, pov_pid=pov, did=discard_id, last_action=last_action)


def run_demo(seed=None, human_pid: Optional[int] = 0, bot: str = "auto"):
    rules = Ruleset(
        include_flowers=True,
        dead_wall_mode="fixed",
        dead_wall_base=16,
        scoring_profile="gametower_star31",
        see_flower_see_wind=False,
        scoring_overrides_path=None,
    )
    env = Mahjong16Env(rules, seed=seed)
    print("=== mahjong16 demo（Rich Console UI） ===")

    obs = env.reset()
    discard_id = 0
    strategies = build_strategies(env.rules.n_players, human_pid, bot)

    while True:
        update_ui(env, human_pid, discard_id, last_action=None)

        act = strategies[obs.get("player")].choose(obs)

        atype = (act.get("type") or "").upper()
        if obs.get("phase") == "TURN" and atype in ("HU", "GANG", "PONG", "CHI"):
            Formatter.print_action_line(act, obs)

        pre_pid = obs.get("player")
        pre_tile = act.get("tile") if atype == "DISCARD" else None

        obs, rew, done, info = env.step(act)

        event = summarize_resolved_claim(info) if isinstance(info, dict) else None
        if event:
            update_ui(env, human_pid, discard_id, last_action=event)

        if atype == "DISCARD" and pre_tile is not None:
            discard_id += 1
            update_ui(
                env,
                human_pid,
                discard_id,
                last_action={"who": f"P{pre_pid}", "type": "DISCARD", "detail": tile_to_str(pre_tile)},
            )

        if done:
            print("=== round end ===")
            print(f"rewards: {rew}")
            rewards2, bd = score_with_breakdown(env)
            winner = env.winner
            if winner is not None:
                print(f"breakdown for P{winner}:")
                for item in bd.get(winner, []):
                    label = item.get("label", item.get("key"))
                    base = item.get("base", 0)
                    count = item.get("count", 1)
                    points = item.get("points", base * count)
                    print(f"  - {label}: {base} x {count} = {points}")
                print(f"total = {sum(i.get('points', 0) for i in bd.get(winner, []))}")
            render_reveal(env)
            break

        if discard_id > 2000:
            print("=== stop (safety break) ===")
            break

