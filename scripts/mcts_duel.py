"""Pit upgraded and legacy MCTS bots against each other and summarise win rates."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.table import TableManager
from bots.mcts import MCTSBot, MCTSBotConfig
from core import Mahjong16Env, Ruleset

TABLE_SIZE = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hands", type=int, default=1000, help="Hands to simulate (default: 1000)")
    parser.add_argument("--seed", type=int, default=0, help="Base RNG seed (default: 0)")
    parser.add_argument("--simulations", type=int, default=96, help="Simulations per decision (default: 96)")
    parser.add_argument("--rollout-depth", type=int, default=8, help="Rollout depth (default: 8)")
    parser.add_argument("--puct-c", type=float, default=1.2, help="Exploration constant for the upgraded bot")
    parser.add_argument("--pw-alpha", type=float, default=0.55, help="Progressive widening exponent for the upgraded bot")
    parser.add_argument("--threads", type=int, default=4, help="Threads for the upgraded bot (default: 4)")
    parser.add_argument("--legacy-puct", type=float, default=1.4, help="Exploration constant for the legacy bot")
    parser.add_argument("--legacy-pw-alpha", type=float, default=0.5, help="Progressive widening exponent for the legacy bot")
    parser.add_argument("--legacy-threads", type=int, default=1, help="Threads for the legacy bot (default: 1)")
    parser.add_argument("--json-out", type=Path, help="Optional JSON path for duel metrics")
    return parser.parse_args()


def ensure_legal_actions(obs: Mapping[str, Any], env: Mahjong16Env, pid: int) -> list[dict]:
    actions = list(obs.get("legal_actions", []) if isinstance(obs, Mapping) else [])
    if actions:
        return actions  # type: ignore[return-value]
    fallback = env.legal_actions(pid)
    if isinstance(obs, dict) and fallback:
        obs["legal_actions"] = fallback
    return fallback


def build_configs(args: argparse.Namespace) -> tuple[MCTSBotConfig, MCTSBotConfig]:
    upgraded = MCTSBotConfig(
        simulations=args.simulations,
        rollout_depth=args.rollout_depth,
        puct_c=args.puct_c,
        pw_alpha=args.pw_alpha,
        threads=args.threads,
    )
    legacy = MCTSBotConfig(
        simulations=args.simulations,
        rollout_depth=args.rollout_depth,
        puct_c=args.legacy_puct,
        pw_alpha=args.legacy_pw_alpha,
        threads=args.legacy_threads,
    )
    return upgraded, legacy


def build_bots(env: Mahjong16Env, upgraded: MCTSBotConfig, legacy: MCTSBotConfig) -> list[MCTSBot]:
    bots: list[MCTSBot] = []
    base_seed = getattr(env, "seed", None)
    for seat in range(TABLE_SIZE):
        config = upgraded if seat % 2 == 0 else legacy
        seat_seed = (base_seed or 0) + seat if base_seed is not None else None
        bots.append(MCTSBot(env, config=replace(config, seed=seat_seed)))
    return bots


def run_duel(args: argparse.Namespace) -> dict[str, Any]:
    rules = Ruleset(include_flowers=False, scoring_profile="taiwan_base", randomize_seating_and_dealer=True)
    env = Mahjong16Env(rules, seed=args.seed)
    table = TableManager(rules, seed=args.seed)
    table.initialize(TABLE_SIZE)

    upgraded_cfg, legacy_cfg = build_configs(args)
    bots = build_bots(env, upgraded_cfg, legacy_cfg)
    metrics = {
        "wins": Counter(),
        "draws": 0,
        "hands_played": 0,
        "new_metrics": {"simulations": 0, "duration": 0.0, "depth_total": 0, "depth_max": 0},
        "legacy_metrics": {"simulations": 0, "duration": 0.0, "depth_total": 0, "depth_max": 0},
    }

    start = time.perf_counter()
    for _ in range(max(0, args.hands)):
        obs = table.start_hand(env)
        done = False
        while not done:
            pid = int(obs.get("player", env.turn)) if isinstance(obs, Mapping) else env.turn
            legal = ensure_legal_actions(obs, env, pid)
            choose_start = time.perf_counter()
            action = bots[pid].choose(obs)
            choose_duration = time.perf_counter() - choose_start
            stats = getattr(bots[pid], "last_stats", None)
            bucket = "new_metrics" if pid % 2 == 0 else "legacy_metrics"
            if stats is not None and getattr(stats, "simulations", 0):
                metrics[bucket]["simulations"] += int(stats.simulations)
                metrics[bucket]["depth_total"] += int(stats.total_depth)
                metrics[bucket]["depth_max"] = max(metrics[bucket]["depth_max"], int(stats.max_depth))
                metrics[bucket]["duration"] += choose_duration
            if isinstance(action, Mapping):
                action = dict(action)
            if legal and action not in legal:
                action = legal[0]
            obs, _reward, done, _info = env.step(action)
        metrics["hands_played"] += 1
        winner = getattr(env, "winner", None)
        if winner is None:
            metrics["draws"] += 1
        else:
            metrics["wins"]["new" if winner % 2 == 0 else "legacy"] += 1
        table.finish_hand(env)

    metrics["elapsed_seconds"] = time.perf_counter() - start
    return metrics


def summarise(metrics: Mapping[str, Any]) -> None:
    print("=== MCTS Duel Summary ===")
    print(f"Hands played     : {metrics.get('hands_played')}")
    print(f"Elapsed seconds  : {metrics.get('elapsed_seconds'):.3f}")
    wins: Counter[str] = metrics.get("wins", Counter())  # type: ignore[assignment]
    draws = metrics.get("draws", 0)
    total = metrics.get("hands_played", 1) or 1
    new_wins = wins.get("new", 0)
    legacy_wins = wins.get("legacy", 0)
    print(f"New bot wins     : {new_wins} ({new_wins / total:.2%})")
    print(f"Legacy bot wins  : {legacy_wins} ({legacy_wins / total:.2%})")
    print(f"Draws            : {draws}")
    for label in ("new_metrics", "legacy_metrics"):
        data = metrics.get(label) or {}
        sims = data.get("simulations", 0)
        duration = data.get("duration", 0.0)
        if not sims:
            continue
        side = "Upgraded" if label == "new_metrics" else "Legacy"
        rate = sims / duration if duration else 0.0
        avg_depth = data.get("depth_total", 0) / sims
        print(f"{side} sims      : {sims} (avg depth {avg_depth:.2f}, sims/sec {rate:.2f})")
        print(f"{side} max depth : {data.get('depth_max', 0)}")


def main() -> None:
    args = parse_args()
    metrics = run_duel(args)
    summarise(metrics)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"Metrics written to {args.json_out}")


if __name__ == "__main__":
    main()
