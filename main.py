"""CLI entrypoint for the Mahjong16 demo.

Provides flags for RNG seed, selecting a human player, and bot strategy.
Delegates the gameplay loop to `app.runtime.run_demo`.
"""

from __future__ import annotations
from app.runtime import run_demo


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="mahjong16 demo CLI")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (int). Omit for random.")
    parser.add_argument(
        "--human",
        type=str,
        default="-1",
        help="Human player id (0-3), or 'none' for no human (all bots). Default: 0",
    )
    parser.add_argument(
        "--bot",
        type=str,
        default="greedy",
        choices=["auto", "greedy", "human"],
        help="Bot strategy for non-human players. Default: greedy",
    )
    parser.add_argument(
        "--hands",
        type=int,
        default=-1,
        help="Number of hands to play (>=1). Use -1 to play until a player drops below 0. Default: 1",
    )
    parser.add_argument(
        "--start-points",
        type=int,
        default=1000,
        help="Starting points allocated to each player. Default: 1000",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default=None,
        help="Optional directory for per-hand summary logs (timestamped CSV). Default: disabled",
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Run headless (disable interactive console UI). Implies logging unless overridden.",
    )
    args = parser.parse_args()

    human_str = (args.human or "").strip().lower()
    if human_str in ("none", "-1", "no", "n"):
        human_pid = None
    else:
        try:
            human_pid = int(args.human)
        except ValueError:
            raise SystemExit("Invalid --human value. Use 0-3 or 'none'.")
        if human_pid not in (0, 1, 2, 3):
            raise SystemExit("Invalid --human value. Must be 0,1,2,3 or 'none'.")

    if args.hands is not None and (args.hands == 0 or args.hands < -1):
        raise SystemExit("Invalid --hands value. Must be -1 or >= 1.")

    try:
        start_points = int(args.start_points)
    except Exception:  # pragma: no cover - argparse already enforces int
        raise SystemExit("Invalid --start-points value. Must be an integer.")

    if start_points <= 0:
        raise SystemExit("Invalid --start-points value. Must be > 0.")

    enable_ui = not args.no_ui
    log_dir = args.log_dir
    if not enable_ui and not log_dir:
        log_dir = "logs"
    if not enable_ui:
        human_pid = None

    run_demo(
        seed=args.seed,
        human_pid=human_pid,
        bot=args.bot,
        hands=args.hands,
        start_points=start_points,
        log_dir=log_dir,
        enable_ui=enable_ui,
    )
