from __future__ import annotations
from typing import Dict, Any, Optional
from core import Mahjong16Env, Ruleset
from core.tiles import tile_to_str
from core.scoring.tables import load_scoring_assets
from core.scoring.types import ScoringContext
from core.scoring.engine import score_with_breakdown
from ui.console import render_public_view, render_reveal
from .table import TableManager
from .strategies import build_strategies


def summarize_resolved_claim(info: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Extract minimal info for a resolved claim to display in the top bar.

    Args:
      info: The info object returned by ``env.step``.

    Returns:
      A dict {who, type, detail} for display, or None if not applicable.
    """
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
    """Render the public view and optionally annotate the latest action.

    Args:
      env: Environment to render.
      human_pid: Point‑of‑view player id (None means 0).
      discard_id: Incremental discard counter for display.
      last_action: Optional {who,type,detail} summary to show.
    """
    pov = (human_pid if human_pid is not None else 0)
    render_public_view(env, pov_pid=pov, did=discard_id, last_action=last_action)


def run_demo(seed=None, human_pid: Optional[int] = 0, bot: str = "auto", hands: int = 1):
    """Run a simple console demo with auto/human play and scoring breakdown.

    Args:
      seed: RNG seed.
      human_pid: Which player index is controlled by human (None for all auto).
      bot: Strategy name (currently 'auto').
    """
    rules = Ruleset(
        include_flowers=True,
        dead_wall_mode="fixed",
        dead_wall_base=16,
        scoring_profile="taiwan_base",
        see_flower_see_wind=False,
        randomize_seating_and_dealer=True,
        enable_wind_flower_scoring=True,
        scoring_overrides_path=None,
    )
    env = Mahjong16Env(rules, seed=seed)
    # Preload scoring table for this run
    table = load_scoring_assets(rules.scoring_profile, rules.scoring_overrides_path)
    print("=== mahjong16 demo（Rich Console UI） ===")

    # Table manager: multi-hand flow
    tm = TableManager(rules, seed=seed)
    tm.initialize(env.rules.n_players)
    strategies = build_strategies(env.rules.n_players, human_pid, bot)

    for hand_idx in range(hands):
        obs = tm.start_hand(env)
        discard_id = 0
        last_seen_discard: Optional[tuple] = None  # (pid, tile)

        # quick header per hand
        print(f"--- Hand {hand_idx+1} | Quan={getattr(env,'quan_feng','?')} | Dealer=P{getattr(env,'dealer_pid',0)} | Streak={getattr(env,'dealer_streak',0)} ---")

        while True:

            act = strategies[obs.get("player")].choose(obs)

            atype = (act.get("type") or "").upper()

            pre_pid = obs.get("player")
            pre_tile = act.get("tile") if atype == "DISCARD" else None

            obs, rew, done, info = env.step(act)

            # Only redraw UI on specific events to avoid duplicates
            event = summarize_resolved_claim(info) if isinstance(info, dict) else None
            if event:
                # RESOLVED_CLAIM: a reaction decision (HU/GANG/PONG/CHI or PASS-all)
                update_ui(env, human_pid, discard_id, last_action=event)

            if atype == "DISCARD" and pre_tile is not None:
                # Record the explicit discard we just took
                discard_id += 1
                last_seen_discard = (pre_pid, pre_tile)
                update_ui(
                    env,
                    human_pid,
                    discard_id,
                    last_action={"who": f"P{pre_pid}", "type": "DISCARD", "detail": tile_to_str(pre_tile)},
                )

            # If a new reaction window opens for the human due to someone else's discard
            # (e.g., our previous action was PASS and env advanced internally),
            # make sure we refresh the board to show that latest discard.
            if (
                obs.get("phase") == "REACTION"
                and human_pid is not None
                and obs.get("player") == human_pid
            ):
                ld = getattr(env, "last_discard", None)
                if isinstance(ld, dict) and ld.get("tile") is not None:
                    key = (ld.get("pid"), ld.get("tile"))
                    # Only refresh if we haven't just rendered this same discard
                    if key != last_seen_discard:
                        discard_id += 1
                        last_seen_discard = key
                        update_ui(
                            env,
                            human_pid,
                            discard_id,
                            last_action={
                                "who": f"P{ld.get('pid')}",
                                "type": "DISCARD",
                                "detail": tile_to_str(ld.get("tile")),
                            },
                        )

            if done:
                print("=== round end ===")
                print(f"rewards: {rew}")
                rewards2, bd = score_with_breakdown(ScoringContext.from_env(env, table))
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
                # ROUND_END: reveal and stop
                render_reveal(env)
                # Update table state and possibly continue to next hand
                tm.finish_hand(env)
                break

            if discard_id > 2000:
                print("=== stop (safety break) ===")
                break

    print("=== demo finished ===")
