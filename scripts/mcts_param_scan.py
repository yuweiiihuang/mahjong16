"""Sweep MCTS hyper-parameters and report aggregate performance metrics."""
from __future__ import annotations

import argparse
import json
import sys
from itertools import product
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import bench_sim


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hands", type=int, default=64, help="Hands simulated per configuration (default: 64)")
    parser.add_argument("--seed", type=int, default=0, help="Base RNG seed shared across runs (default: 0)")
    parser.add_argument("--simulations", type=int, default=64, help="Simulations per decision (default: 64)")
    parser.add_argument("--rollout-depth", type=int, default=6, help="Rollout depth for each simulation (default: 6)")
    parser.add_argument("--threads", type=int, default=1, help="Threads allocated to each configuration (default: 1)")
    parser.add_argument("--pw-c", type=float, default=1.5, help="Progressive widening growth constant (default: 1.5)")
    parser.add_argument(
        "--c-puct",
        type=float,
        nargs="+",
        default=[0.8, 1.0, 1.2, 1.4],
        help="List of exploration constants to evaluate",
    )
    parser.add_argument(
        "--pw-alpha",
        type=float,
        nargs="+",
        default=[0.4, 0.5, 0.6],
        help="List of progressive widening exponents to evaluate",
    )
    parser.add_argument("--json-out", type=Path, help="Optional JSON output path for full results")
    parser.add_argument("--skip-scoring", action="store_true", help="Skip scoring to focus on search throughput")
    parser.add_argument("--no-flowers", action="store_true", help="Disable flowers during evaluation")
    return parser.parse_args()


def _make_namespace(args: argparse.Namespace, c_puct: float, pw_alpha: float) -> argparse.Namespace:
    return argparse.Namespace(
        hands=args.hands,
        seed=args.seed,
        bot="mcts",
        profile="taiwan_base",
        scoring_json=None,
        skip_scoring=args.skip_scoring,
        no_flowers=args.no_flowers,
        dead_wall_mode="fixed",
        dead_wall_base=16,
        mcts_simulations=args.simulations,
        mcts_uct=c_puct,
        mcts_depth=args.rollout_depth,
        mcts_pw_alpha=pw_alpha,
        mcts_pw_c=args.pw_c,
        mcts_seed=args.seed,
        mcts_threads=args.threads,
        mcts_processes=0,
        json_out=None,
    )


def run_scan(args: argparse.Namespace) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for c_puct, pw_alpha in product(args.c_puct, args.pw_alpha):
        ns = _make_namespace(args, c_puct, pw_alpha)
        metrics = bench_sim.run_benchmark(ns)
        summary = {
            "c_puct": c_puct,
            "pw_alpha": pw_alpha,
            "hands_per_second": metrics.get("hands_per_second", 0.0),
            "mcts_simulations_per_second": metrics.get("mcts_simulations_per_second", 0.0),
            "mcts_avg_depth": metrics.get("mcts_avg_depth", 0.0),
            "mcts_max_depth": metrics.get("mcts_max_depth", 0),
            "simulations": metrics.get("mcts_simulations", 0),
        }
        results.append(summary)
    return results


def print_table(results: Iterable[dict[str, Any]]) -> None:
    header = f"{'c_puct':>7} {'pw_alpha':>8} {'hands/s':>10} {'sims/s':>10} {'avg_depth':>10} {'max_depth':>10}"
    print(header)
    print("-" * len(header))
    for row in results:
        print(
            f"{row['c_puct']:7.3f} {row['pw_alpha']:8.3f} "
            f"{row['hands_per_second']:10.3f} {row['mcts_simulations_per_second']:10.3f} "
            f"{row['mcts_avg_depth']:10.3f} {row['mcts_max_depth']:10d}"
        )


def main() -> None:
    args = parse_args()
    results = run_scan(args)
    print_table(results)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Results written to {args.json_out}")


if __name__ == "__main__":
    main()
