"""Benchmark Mahjong16 environment throughput over simulated hands."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

TABLE_SIZE = 4

# Ensure the project root (two levels up) is importable when invoked as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.table import TableManager
from app.strategies import AutoStrategy
from bots.greedy import GreedyBotStrategy
from bots.mcts import MCTSBot, MCTSBotConfig
from bots.random_bot import RandomBot
from bots.rulebot import RuleBot
from core import Mahjong16Env, Ruleset
from core.scoring.engine import compute_payments, score_with_breakdown
from core.scoring.tables import load_scoring_assets
from core.scoring.types import ScoringContext


@dataclass
class StrategyWrapper:
    """Normalise strategy interfaces to expose a ``choose`` method."""

    impl: Any

    def choose(self, obs: Mapping[str, Any]) -> Mapping[str, Any]:
        if hasattr(self.impl, "choose"):
            return self.impl.choose(obs)
        if hasattr(self.impl, "select"):
            return self.impl.select(obs)
        raise TypeError(f"Strategy object {self.impl!r} does not support choose/select")


def build_strategy(
    alias: str,
    seat_index: int,
    base_seed: int | None,
    env: Mahjong16Env,
    args: argparse.Namespace,
) -> StrategyWrapper:
    """Instantiate a benchmark bot for the given seat."""

    alias_norm = alias.lower()
    seed = base_seed + seat_index if base_seed is not None else None
    if alias_norm in {"auto"}:
        impl = AutoStrategy()
    elif alias_norm in {"greedy", "greedybot"}:
        impl = GreedyBotStrategy()
    elif alias_norm in {"mcts", "mctsbot"}:
        cfg_seed = args.mcts_seed if args.mcts_seed is not None else seed
        config = MCTSBotConfig(
            simulations=int(args.mcts_simulations),
            puct_c=float(args.mcts_uct),
            rollout_depth=int(args.mcts_depth),
            seed=cfg_seed,
            threads=int(getattr(args, "mcts_threads", 1)),
            processes=int(getattr(args, "mcts_processes", 0)),
            pw_alpha=float(getattr(args, "mcts_pw_alpha", MCTSBotConfig.pw_alpha)),
            pw_c=float(getattr(args, "mcts_pw_c", MCTSBotConfig.pw_c)),
        )
        impl = MCTSBot(env, config=config)
    elif alias_norm in {"random", "randombot"}:
        impl = RandomBot(seed=seed)
    elif alias_norm in {"rule", "rulebot"}:
        impl = RuleBot()
    else:
        raise SystemExit(f"Unknown bot alias: {alias}")
    return StrategyWrapper(impl)


def ensure_legal_actions(obs: Mapping[str, Any], env: Mahjong16Env, pid: int) -> Sequence[Mapping[str, Any]]:
    """Return legal actions from observation or query the environment as fallback."""

    actions = obs.get("legal_actions") if isinstance(obs, Mapping) else None
    if actions:
        return actions  # type: ignore[return-value]
    fallback = env.legal_actions(pid)
    if fallback:
        # Inject fallback actions into observation for downstream strategies expecting the key.
        if isinstance(obs, dict):
            obs.setdefault("legal_actions", fallback)
    return fallback


def to_payments_list(raw: Mapping[int, Any] | Sequence[int], n_players: int) -> list[int]:
    if isinstance(raw, Mapping):
        return [int(raw.get(pid, 0)) for pid in range(n_players)]
    return [int(raw[pid]) if pid < len(raw) else 0 for pid in range(n_players)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--hands", type=int, default=1000, help="Number of hands to simulate (default: 1000)")
    parser.add_argument("--seed", type=int, default=None, help="Base RNG seed for env/table/agents")
    parser.add_argument(
        "--bot",
        default="auto",
        help="Bot alias for every seat (auto/greedy/random/rulebot/mcts)",
    )
    parser.add_argument("--profile", default="taiwan_base", help="Scoring profile key (default: taiwan_base)")
    parser.add_argument("--scoring-json", type=Path, default=None, help="Optional scoring JSON override path")
    parser.add_argument("--skip-scoring", action="store_true", help="Skip scoring to measure env throughput only")
    parser.add_argument("--no-flowers", action="store_true", help="Disable flowers in the wall during benchmark")
    parser.add_argument(
        "--dead-wall-mode",
        choices=["fixed", "gang_plus_one"],
        default="fixed",
        help="Dead-wall reservation mode (default: fixed)",
    )
    parser.add_argument(
        "--dead-wall-base",
        type=int,
        default=16,
        help="Base reserved tiles for the dead wall (default: 16)",
    )
    parser.add_argument(
        "--mcts-simulations",
        type=int,
        default=32,
        help="Number of simulations per decision for mcts bot (default: 32)",
    )
    parser.add_argument(
        "--mcts-uct",
        type=float,
        default=1.4,
        help="UCT exploration constant for mcts bot (default: 1.4)",
    )
    parser.add_argument(
        "--mcts-depth",
        type=int,
        default=12,
        help="Rollout depth limit for mcts bot (default: 12)",
    )
    parser.add_argument(
        "--mcts-pw-alpha",
        type=float,
        default=MCTSBotConfig.pw_alpha,
        help="Progressive widening alpha exponent (default: 0.5)",
    )
    parser.add_argument(
        "--mcts-pw-c",
        type=float,
        default=MCTSBotConfig.pw_c,
        help="Progressive widening growth constant (default: 1.5)",
    )
    parser.add_argument(
        "--mcts-seed",
        type=int,
        default=None,
        help="Optional RNG seed override for mcts bot (per seat offset still applied)",
    )
    parser.add_argument(
        "--mcts-threads",
        type=int,
        default=1,
        help="Number of worker threads for each MCTS bot (default: 1)",
    )
    parser.add_argument(
        "--mcts-processes",
        type=int,
        default=0,
        help="Optional number of process workers for MCTS rollouts (default: 0)",
    )
    parser.add_argument("--json-out", type=Path, help="Write metrics JSON to the given path")
    return parser.parse_args()


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    n_players = TABLE_SIZE
    hands_target = max(0, int(args.hands))
    rules = Ruleset(
        include_flowers=not args.no_flowers,
        n_players=n_players,
        scoring_profile=args.profile,
        scoring_overrides_path=str(args.scoring_json) if args.scoring_json else None,
        dead_wall_mode=args.dead_wall_mode,
        dead_wall_base=int(args.dead_wall_base),
        randomize_seating_and_dealer=True,
    )

    env = Mahjong16Env(rules, seed=args.seed)
    table = TableManager(rules, seed=args.seed)
    table.initialize(n_players)

    strategies = [build_strategy(args.bot, seat, args.seed, env, args) for seat in range(n_players)]

    scoring_table = None
    if not args.skip_scoring:
        override_path = str(args.scoring_json) if args.scoring_json else rules.scoring_overrides_path
        scoring_table = load_scoring_assets(rules.scoring_profile, override_path)

    totals = {
        "hands_played": 0,
        "steps": 0,
        "draws": 0,
        "wins": 0,
        "tsumo_wins": 0,
        "ron_wins": 0,
        "gang_total": 0,
    }
    mcts_metrics = {
        "simulations": 0,
        "depth_total": 0,
        "depth_max": 0,
        "duration": 0.0,
    }
    win_sources: Counter[str] = Counter()
    flower_wins: Counter[str] = Counter()
    payments_accum = [0 for _ in range(n_players)]

    start = time.perf_counter()

    for _ in range(hands_target):
        obs = table.start_hand(env)
        done = False
        while not done:
            pid = int(obs.get("player", env.turn)) if isinstance(obs, Mapping) else env.turn
            legal = ensure_legal_actions(obs, env, pid) or []
            choose_start = time.perf_counter()
            try:
                action = strategies[pid].choose(obs)
            except Exception:
                action = {"type": "PASS"}
            choose_duration = time.perf_counter() - choose_start

            impl = strategies[pid].impl
            stats = getattr(impl, "last_stats", None)
            sims = int(getattr(stats, "simulations", 0)) if stats is not None else 0
            if sims:
                mcts_metrics["simulations"] += sims
                mcts_metrics["depth_total"] += int(getattr(stats, "total_depth", 0))
                mcts_metrics["depth_max"] = max(
                    mcts_metrics["depth_max"], int(getattr(stats, "max_depth", 0))
                )
                mcts_metrics["duration"] += choose_duration
            if isinstance(action, Mapping):
                action = dict(action)
            if not isinstance(action, dict) or not action:
                action = {"type": "PASS"}
            if legal and action not in legal:
                # Defensive fallback when strategy returns an unexpected dict.
                action = legal[0]
            obs, _reward, done, _info = env.step(action)  # type: ignore[assignment]
            totals["steps"] += 1
        totals["hands_played"] += 1
        winner = getattr(env, "winner", None)
        win_source = str(getattr(env, "win_source", None) or "DRAW").upper()
        win_sources[win_source] += 1
        if winner is None:
            totals["draws"] += 1
        else:
            totals["wins"] += 1
            if win_source in {"TSUMO", "ZIMO"}:
                totals["tsumo_wins"] += 1
            elif win_source == "RON":
                totals["ron_wins"] += 1
        flower_type = getattr(env, "flower_win_type", None)
        if flower_type:
            flower_wins[str(flower_type)] += 1
        totals["gang_total"] += int(getattr(env, "n_gang", 0) or 0)

        if scoring_table is not None:
            ctx = ScoringContext.from_env(env, scoring_table)
            rewards, breakdown = score_with_breakdown(ctx)
            payments_raw, _ = compute_payments(
                ctx,
                getattr(rules, "base_points", 100),
                getattr(rules, "tai_points", 20),
                rewards=rewards,
                breakdown=breakdown,
            )
            payments = to_payments_list(payments_raw, n_players)
            for idx, delta in enumerate(payments):
                payments_accum[idx] += int(delta)

        table.finish_hand(env)

    elapsed = time.perf_counter() - start

    steps = totals["steps"] or 1
    hands_played = totals["hands_played"] or 1
    metrics: dict[str, Any] = {
        "hands_requested": hands_target,
        "hands_played": totals["hands_played"],
        "draws": totals["draws"],
        "wins": totals["wins"],
        "tsumo_wins": totals["tsumo_wins"],
        "ron_wins": totals["ron_wins"],
        "win_sources": dict(win_sources),
        "flower_wins": dict(flower_wins),
        "gang_total": totals["gang_total"],
        "elapsed_seconds": elapsed,
        "hands_per_second": totals["hands_played"] / elapsed if elapsed > 0 else None,
        "steps_per_second": totals["steps"] / elapsed if elapsed > 0 else None,
        "avg_steps_per_hand": totals["steps"] / hands_played,
        "avg_time_per_hand": elapsed / hands_played,
        "avg_time_per_step": elapsed / steps,
    }
    if mcts_metrics["simulations"]:
        metrics["mcts_simulations"] = mcts_metrics["simulations"]
        metrics["mcts_avg_depth"] = (
            mcts_metrics["depth_total"] / mcts_metrics["simulations"]
        )
        metrics["mcts_max_depth"] = mcts_metrics["depth_max"]
    if mcts_metrics["duration"] > 0:
        metrics["mcts_simulations_per_second"] = (
            mcts_metrics["simulations"] / mcts_metrics["duration"]
        )
    if scoring_table is not None:
        metrics["payments_total"] = payments_accum
        metrics["payments_avg_per_hand"] = [
            (value / hands_played) if hands_played else 0 for value in payments_accum
        ]
    return metrics


def print_summary(metrics: Mapping[str, Any]) -> None:
    print("=== Mahjong16 Benchmark ===")
    print(f"Hands requested : {metrics.get('hands_requested')}")
    print(f"Hands played    : {metrics.get('hands_played')}")
    print(f"Elapsed (s)     : {metrics.get('elapsed_seconds'):.3f}")
    hps = metrics.get("hands_per_second")
    sps = metrics.get("steps_per_second")
    if hps is not None:
        print(f"Hands / second : {hps:.2f}")
    if sps is not None:
        print(f"Steps / second : {sps:.2f}")
    print(f"Avg steps/hand : {metrics.get('avg_steps_per_hand'):.2f}")
    print(f"Avg time/hand  : {metrics.get('avg_time_per_hand'):.4f} s")
    print(f"Draws          : {metrics.get('draws')}")
    print(f"Wins           : {metrics.get('wins')} (tsumo={metrics.get('tsumo_wins')}, ron={metrics.get('ron_wins')})")
    sims = metrics.get("mcts_simulations")
    if sims:
        print(f"MCTS sims      : {int(sims)}")
        rate = metrics.get("mcts_simulations_per_second")
        if rate:
            print(f"MCTS sims/sec  : {rate:.2f}")
        avg_depth = metrics.get("mcts_avg_depth")
        if avg_depth is not None:
            print(f"MCTS avg depth : {avg_depth:.2f}")
        print(f"MCTS max depth : {int(metrics.get('mcts_max_depth', 0))}")
    win_sources = metrics.get("win_sources") or {}
    if win_sources:
        items = ", ".join(f"{k}:{v}" for k, v in sorted(win_sources.items()))
        print(f"Win sources    : {items}")
    flower_wins = metrics.get("flower_wins") or {}
    if flower_wins:
        items = ", ".join(f"{k}:{v}" for k, v in sorted(flower_wins.items()))
        print(f"Flower wins    : {items}")
    print(f"Total gangs    : {metrics.get('gang_total')}")
    payments = metrics.get("payments_total")
    if payments:
        avg = metrics.get("payments_avg_per_hand") or []
        print("Payments total : [" + ", ".join(str(v) for v in payments) + "]")
        print("Payments/hand  : [" + ", ".join(f"{v:.2f}" for v in avg) + "]")


def main() -> None:
    args = parse_args()
    metrics = run_benchmark(args)
    print_summary(metrics)
    json_out: Path | None = getattr(args, "json_out", None)
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"Metrics written to {json_out}")


if __name__ == "__main__":
    main()
