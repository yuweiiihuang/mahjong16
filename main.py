"""CLI entrypoint for the Mahjong16 demo.

Provides simple flags for RNG seed, selecting a human player, and bot strategy.
Delegates to `app.runtime.run_demo_ui` or `app.runtime.run_demo_headless`.
"""

from __future__ import annotations
from app.runtime import run_demo_headless, run_demo_headless_batch, run_demo_ui, run_demo_web


if __name__ == "__main__":
    import argparse

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
        help="Number of hands to play (>=1). Use -1 to play until a player drops below 0. Default: -1",
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
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the FastAPI web interface instead of the console UI.",
    )
    parser.add_argument(
        "--web-host",
        type=str,
        default="0.0.0.0",
        help="Bind host for the web interface. Default: 0.0.0.0",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=8000,
        help="Bind port for the web interface. Default: 8000",
    )
    parser.add_argument(
        "--web-log-level",
        type=str,
        default="info",
        help="Uvicorn log level for the web interface. Default: info",
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
    if args.jangs < 0:
        raise SystemExit("Invalid --jangs value. Must be >= 0.")
    if args.jangs > 0 and args.hands not in (-1, None):
        raise SystemExit("Cannot combine --jangs with a finite --hands value.")

    try:
        start_points = int(args.start_points)
    except Exception:  # pragma: no cover - argparse already enforces int
        raise SystemExit("Invalid --start-points value. Must be an integer.")

    if start_points <= 0:
        raise SystemExit("Invalid --start-points value. Must be > 0.")

    if args.sessions < 1:
        raise SystemExit("Invalid --sessions value. Must be >= 1.")
    if args.cores is not None and args.cores < 1:
        raise SystemExit("Invalid --cores value. Must be >= 1 when provided.")

    sessions = args.sessions
    cores = args.cores
    if args.web:
        if args.no_ui:
            raise SystemExit("Cannot combine --web with --no-ui.")
        if sessions > 1 or (cores is not None and cores > 1):
            raise SystemExit("--web does not support multi-session or multi-core execution.")
        run_demo_web(
            seed=args.seed,
            human_pid=human_pid,
            bot=args.bot,
            hands=args.hands,
            jangs=args.jangs,
            start_points=start_points,
            host=args.web_host,
            port=args.web_port,
            log_level=args.web_log_level,
        )
        return

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
            start_points=start_points,
            log_dir=log_dir,
        )
    else:
        runner = run_demo_ui if enable_ui else run_demo_headless
        runner(
            seed=args.seed,
            human_pid=human_pid,
            bot=args.bot,
            hands=args.hands,
            jangs=args.jangs,
            start_points=start_points,
            log_dir=log_dir,
        )
