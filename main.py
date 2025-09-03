"""CLI entrypoint for the Mahjong16 demo.

Provides simple flags for RNG seed, selecting a human player, and bot strategy.
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
        default="0",
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
        default=1,
        help="Number of hands to play (>=1). Default: 1",
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

    if args.hands is not None and args.hands < 1:
        raise SystemExit("Invalid --hands value. Must be >= 1.")

    run_demo(seed=args.seed, human_pid=human_pid, bot=args.bot, hands=args.hands)
