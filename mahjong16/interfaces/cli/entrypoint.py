"""Command-line entrypoint for the Mahjong16 demo application."""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from sdk import build_headless_session, build_ui_session, run_demo_headless_batch


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Return parsed CLI arguments for the Mahjong16 demo."""

    parser = argparse.ArgumentParser(description="mahjong16 demo CLI")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (int). Omit for random.")
    parser.add_argument(
        "--human",
        type=str,
        default="-1",
        help="Human player id (0-3), or 'none' for no human (all bots). Default: -1",
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
        help="Number of hands to play (>=1). Use -1 to play until a player drops below 0.",
    )
    parser.add_argument(
        "--jangs",
        type=int,
        default=0,
        help="Number of jangs (四圈) to play (>=1). Use 0 to disable. Conflicts with --hands >= 1.",
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
    parser.add_argument(
        "--sessions",
        type=int,
        default=1,
        help="Number of independent sessions to simulate. Default: 1",
    )
    parser.add_argument(
        "--cores",
        type=int,
        default=None,
        help="Maximum worker processes for headless batches. Default: auto",
    )
    return parser.parse_args(argv)


def _normalize_human_pid(raw: str) -> Optional[int]:
    value = (raw or "").strip().lower()
    if value in {"none", "-1", "no", "n", ""}:
        return None
    try:
        pid = int(raw)
    except ValueError as exc:  # pragma: no cover - argparse already enforces str
        raise SystemExit("Invalid --human value. Use 0-3 or 'none'.") from exc
    if pid not in (0, 1, 2, 3):
        raise SystemExit("Invalid --human value. Must be 0,1,2,3 or 'none'.")
    return pid


def _validate_args(args: argparse.Namespace) -> None:
    if args.hands is not None and (args.hands == 0 or args.hands < -1):
        raise SystemExit("Invalid --hands value. Must be -1 or >= 1.")
    if args.jangs < 0:
        raise SystemExit("Invalid --jangs value. Must be >= 0.")
    if args.jangs > 0 and args.hands not in (-1, None):
        raise SystemExit("Cannot combine --jangs with a finite --hands value.")
    if args.start_points <= 0:
        raise SystemExit("Invalid --start-points value. Must be > 0.")
    if args.sessions < 1:
        raise SystemExit("Invalid --sessions value. Must be >= 1.")
    if args.cores is not None and args.cores < 1:
        raise SystemExit("Invalid --cores value. Must be >= 1 when provided.")


def run_from_args(args: argparse.Namespace) -> None:
    """Execute the CLI using the provided argument namespace."""

    _validate_args(args)
    human_pid = _normalize_human_pid(args.human)

    sessions = args.sessions
    cores = args.cores
    enable_ui = not args.no_ui
    if sessions > 1 or (cores is not None and cores > 1):
        enable_ui = False
    log_dir = args.log_dir
    if not enable_ui and not log_dir:
        log_dir = "logs"
    if not enable_ui:
        human_pid = None

    if sessions > 1 or (cores is not None and cores > 1):
        run_demo_headless_batch(
            sessions=sessions,
            cores=cores,
            seed=args.seed,
            bot=args.bot,
            hands=args.hands,
            jangs=args.jangs,
            start_points=args.start_points,
            log_dir=log_dir,
        )
        return

    if enable_ui:
        session = build_ui_session(
            seed=args.seed,
            human_pid=human_pid,
            bot=args.bot,
            hands=args.hands,
            jangs=args.jangs,
            start_points=args.start_points,
            log_dir=log_dir,
        )
    else:
        session = build_headless_session(
            seed=args.seed,
            bot=args.bot,
            hands=args.hands,
            jangs=args.jangs,
            start_points=args.start_points,
            log_dir=log_dir,
            emit_logs=not enable_ui,
        )
    session.run()


def main(argv: Optional[Sequence[str]] = None) -> None:
    """CLI entry function used by :mod:`python -m mahjong16.interfaces.cli`."""

    args = parse_args(argv)
    run_from_args(args)
