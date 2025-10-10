from __future__ import annotations
import multiprocessing as mp
import os
import random
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from queue import Empty
from typing import Any, Callable, Dict, List, Optional, Tuple

from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TaskProgressColumn,
    TextColumn,
)

from core import Mahjong16Env, Ruleset
from core.tiles import tile_to_str, tile_sort_key
from core.scoring.tables import load_scoring_assets
from core.scoring.types import ScoringContext
from core.scoring.engine import score_with_breakdown, compute_payments
from ui.console import render_public_view, render_reveal, render_winners_summary
from .table import TableManager
from .strategies import build_strategies
from .logging import write_hand_log


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


def update_ui(
    env: Mahjong16Env,
    human_pid: Optional[int],
    discard_id: int,
    last_action: Optional[Dict[str, Any]] = None,
    score_state: Optional[Dict[str, Any]] = None,
) -> None:
    """Render the public view and optionally annotate the latest action.

    Args:
      env: Environment to render.
      human_pid: Point‑of‑view player id (None means 0).
      discard_id: Incremental discard counter for display.
      last_action: Optional {who,type,detail} summary to show.
    """
    pov = (human_pid if human_pid is not None else 0)
    render_public_view(
        env,
        pov_pid=pov,
        did=discard_id,
        last_action=last_action,
        score_state=score_state,
    )

class _BaseDemoRunner:
    """Shared orchestration for Mahjong16 demo sessions."""

    provides_ui: bool = False

    def __init__(
        self,
        *,
        seed=None,
        human_pid: Optional[int] = 0,
        bot: str = "auto",
        hands: int = 1,
        jangs: int = 0,
        start_points: int = 1000,
        log_dir: Optional[str] = None,
        emit_logs: bool = True,
    ) -> None:
        self.seed = seed
        self.human_pid = human_pid
        self.bot = bot
        self.hands = hands
        self.jangs = jangs
        self.log_dir = log_dir
        self.emit_logs = emit_logs

        self.rules = Ruleset(
            include_flowers=True,
            dead_wall_mode="fixed",
            dead_wall_base=16,
            scoring_profile="taiwan_base",
            randomize_seating_and_dealer=True,
            enable_wind_flower_scoring=True,
            scoring_overrides_path=None,
        )
        self.env = Mahjong16Env(self.rules, seed=seed)
        self.table = load_scoring_assets(self.rules.scoring_profile, self.rules.scoring_overrides_path)

        self.tm = TableManager(self.rules, seed=seed)
        self.tm.initialize(self.env.rules.n_players)
        self.strategies = build_strategies(self.env.rules.n_players, human_pid, bot)

        self.n_players = self.env.rules.n_players
        start_points_value = self._normalize_start_points(start_points)
        self.totals = [start_points_value for _ in range(self.n_players)]
        self.hand_delta = [0 for _ in range(self.n_players)]
        self.score_state = {"totals": self.totals, "deltas": self.hand_delta}

        self.target_jangs = self._normalize_jangs(jangs)
        self.play_until_negative = (hands == -1 and self.target_jangs is None)
        self.max_hands = None if (self.play_until_negative or self.target_jangs is not None) else hands
        self.hand_summaries: list = []

    def run(self) -> None:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    def _execute(self) -> list:
        hand_idx = 0
        while True:
            if self.max_hands is not None and hand_idx >= self.max_hands:
                break

            hand_idx += 1
            obs = self.tm.start_hand(self.env)
            self.hand_delta = [0 for _ in range(self.n_players)]
            self.score_state["deltas"] = self.hand_delta
            discard_id = 0
            last_seen_discard: Optional[tuple] = None

            if getattr(self.env, "done", False):
                if self._process_hand_end(hand_idx):
                    return self._finalize()
                continue

            self.on_hand_start(hand_idx)

            while True:
                acts_current = obs.get("legal_actions") or []
                if not acts_current:
                    recalculated = self.env.legal_actions()
                    if recalculated:
                        obs = dict(obs)
                        obs["legal_actions"] = recalculated
                        acts_current = recalculated
                    elif getattr(self.env, "done", False):
                        if self._process_hand_end(hand_idx):
                            return self._finalize()
                        break
                    else:
                        raise AssertionError(
                            f"No legal actions available for player {obs.get('player')} in phase {obs.get('phase')}."
                        )

                act = self.strategies[obs.get("player")].choose(obs)
                atype = (act.get("type") or "").upper()
                pre_pid = obs.get("player")
                pre_tile = act.get("tile") if atype == "DISCARD" else None

                obs, _rew, done, info = self.env.step(act)
                discard_id, last_seen_discard = self.after_step(
                    obs=obs,
                    info=info,
                    discard_id=discard_id,
                    last_seen_discard=last_seen_discard,
                    act=act,
                    action_type=atype,
                    acting_pid=pre_pid,
                    discarded_tile=pre_tile,
                )

                if done:
                    if self._process_hand_end(hand_idx):
                        return self._finalize()
                    break

                if discard_id > 2000:
                    if self.emit_logs:
                        print("=== stop (safety break) ===")
                    break

        return self._finalize()

    def on_session_start(self) -> None:
        """Hook for subclasses to announce the session."""

    def on_hand_start(self, hand_idx: int) -> None:
        """Hook invoked at the start of each hand."""

    def after_step(
        self,
        *,
        obs: Dict[str, Any],
        info: Optional[Dict[str, Any]],
        discard_id: int,
        last_seen_discard: Optional[tuple],
        act: Dict[str, Any],
        action_type: str,
        acting_pid: Optional[int],
        discarded_tile,
    ) -> tuple[int, Optional[tuple]]:
        """Hook invoked after each env.step call."""
        return discard_id, last_seen_discard

    def on_hand_scored(self, breakdown, payments) -> None:
        """Hook invoked once scoring is complete for a hand."""

    def on_hand_complete(self, hand_idx: int) -> None:
        """Hook invoked after TableManager updates for the hand."""

    def _process_hand_end(self, hand_idx: int) -> bool:
        ctx = ScoringContext.from_env(self.env, self.table)
        rewards2, bd = score_with_breakdown(ctx)
        payments_raw, _ = compute_payments(
            ctx,
            getattr(self.env.rules, "base_points", 100),
            getattr(self.env.rules, "tai_points", 20),
            rewards=rewards2,
            breakdown=bd,
        )
        payments = [0 for _ in range(self.n_players)]
        for pid in range(self.n_players):
            delta = 0
            try:
                delta = int(payments_raw[pid])
            except Exception:
                delta = 0
            payments[pid] = delta
            self.totals[pid] += delta
            self.hand_delta[pid] = delta

        winner = self.env.winner
        if winner is not None:
            try:
                pl = self.env.players[winner]
                get = pl.get if isinstance(pl, dict) else lambda key, default=None: getattr(pl, key, default)
                hand_tiles = sorted(list(get("hand") or []), key=tile_sort_key)
                melds = [m if isinstance(m, dict) else {} for m in (get("melds") or [])]
                flowers = sorted(list(get("flowers") or []), key=tile_sort_key)
                win_src = (getattr(self.env, "win_source", None) or "").upper()
                ron_from = getattr(self.env, "turn_at_win", None) if win_src == "RON" else None
                win_tile = getattr(self.env, "win_tile", None)
                qf = getattr(self.env, "quan_feng", None)
                dealer_pid = getattr(self.env, "dealer_pid", None)
                seat_winds = getattr(self.env, "seat_winds", None)
                dealer_wind = None
                winner_wind = None
                try:
                    if isinstance(seat_winds, list):
                        if isinstance(dealer_pid, int) and 0 <= dealer_pid < len(seat_winds):
                            dealer_wind = seat_winds[dealer_pid]
                        if 0 <= winner < len(seat_winds):
                            winner_wind = seat_winds[winner]
                except Exception:
                    dealer_wind = None
                    winner_wind = None
                self.hand_summaries.append(
                    {
                        "hand_index": hand_idx,
                        "jang_index": getattr(self.tm.state, "jang_count", 0) + 1,
                        "winner": winner,
                        "win_source": win_src,
                        "ron_from": ron_from,
                        "win_tile": win_tile,
                        "hand": hand_tiles,
                        "melds": melds,
                        "flowers": flowers,
                        "breakdown": list(bd.get(winner, [])),
                        "payments": list(payments),
                        "base_points": getattr(self.env.rules, "base_points", None),
                        "tai_points": getattr(self.env.rules, "tai_points", None),
                        "quan_feng": qf,
                        "dealer_pid": dealer_pid,
                        "dealer_wind": dealer_wind,
                        "winner_wind": winner_wind,
                        "totals_after_hand": list(self.totals),
                        "remain_tiles": ctx.wall_len,
                    }
                )
            except Exception:
                pass
        else:
            try:
                qf = getattr(self.env, "quan_feng", None)
                dealer_pid = getattr(self.env, "dealer_pid", None)
                seat_winds = getattr(self.env, "seat_winds", None)
                dealer_wind = None
                try:
                    if isinstance(dealer_pid, int) and isinstance(seat_winds, list) and 0 <= dealer_pid < len(seat_winds):
                        dealer_wind = seat_winds[dealer_pid]
                except Exception:
                    dealer_wind = None
                self.hand_summaries.append(
                    {
                        "hand_index": hand_idx,
                        "jang_index": getattr(self.tm.state, "jang_count", 0) + 1,
                        "winner": None,
                        "result": "DRAW",
                        "payments": list(payments),
                        "base_points": getattr(self.env.rules, "base_points", None),
                        "tai_points": getattr(self.env.rules, "tai_points", None),
                        "quan_feng": qf,
                        "dealer_pid": dealer_pid,
                        "dealer_wind": dealer_wind,
                        "totals_after_hand": list(self.totals),
                        "remain_tiles": ctx.wall_len,
                    }
                )
            except Exception:
                pass

        self.on_hand_scored(bd, payments)
        self.tm.finish_hand(self.env)
        self.on_hand_complete(hand_idx)

        if self.target_jangs is not None:
            jang_count = getattr(self.tm.state, "jang_count", 0)
            if jang_count >= self.target_jangs:
                if self.emit_logs:
                    print("=== stop (jang limit reached) ===")
                return True

        if self.play_until_negative and any(pt < 0 for pt in self.totals):
            if self.emit_logs:
                print("=== stop (negative points reached) ===")
            return True
        return False

    def _normalize_start_points(self, start_points: int) -> int:
        try:
            value = int(start_points)
        except Exception:  # pragma: no cover - defensive fallback
            value = 1000
        if value <= 0:
            value = 1
        return value

    def _normalize_jangs(self, jangs: Optional[int]) -> Optional[int]:
        if jangs is None:
            return None
        try:
            value = int(jangs)
        except Exception:  # pragma: no cover - defensive fallback
            return None
        if value <= 0:
            return None
        return value

    def _finalize(self) -> list:
        if self.emit_logs:
            _finalize_demo(self.hand_summaries, log_dir=self.log_dir, enable_ui=self.provides_ui)
        return self.hand_summaries


class _UIDemoRunner(_BaseDemoRunner):
    provides_ui = True

    def run(self) -> None:
        print("=== mahjong16 demo（Rich Console UI） ===")
        self.on_session_start()
        return self._execute()

    def on_session_start(self) -> None:
        # Nothing extra beyond banner for now.
        return None

    def on_hand_start(self, hand_idx: int) -> None:
        jang_idx = getattr(self.tm.state, "jang_count", 0) + 1
        print(
            f"--- Hand {hand_idx} | Jang={jang_idx} | Quan={getattr(self.env,'quan_feng','?')} | "
            f"Dealer=P{getattr(self.env,'dealer_pid',0)} | Streak={getattr(self.env,'dealer_streak',0)} ---"
        )

    def after_step(
        self,
        *,
        obs: Dict[str, Any],
        info: Optional[Dict[str, Any]],
        discard_id: int,
        last_seen_discard: Optional[tuple],
        act: Dict[str, Any],
        action_type: str,
        acting_pid: Optional[int],
        discarded_tile,
    ) -> tuple[int, Optional[tuple]]:
        event = summarize_resolved_claim(info) if isinstance(info, dict) else None
        if event:
            update_ui(
                self.env,
                self.human_pid,
                discard_id,
                last_action=event,
                score_state=self.score_state,
            )

        if action_type == "DISCARD" and discarded_tile is not None:
            discard_id += 1
            last_seen_discard = (acting_pid, discarded_tile)
            update_ui(
                self.env,
                self.human_pid,
                discard_id,
                last_action={"who": f"P{acting_pid}", "type": "DISCARD", "detail": tile_to_str(discarded_tile)},
                score_state=self.score_state,
            )

        if (
            obs.get("phase") == "REACTION"
            and self.human_pid is not None
            and obs.get("player") == self.human_pid
        ):
            ld = getattr(self.env, "last_discard", None)
            if isinstance(ld, dict) and ld.get("tile") is not None:
                key = (ld.get("pid"), ld.get("tile"))
                if key != last_seen_discard:
                    discard_id += 1
                    last_seen_discard = key
                    update_ui(
                        self.env,
                        self.human_pid,
                        discard_id,
                        last_action={
                            "who": f"P{ld.get('pid')}",
                            "type": "DISCARD",
                            "detail": tile_to_str(ld.get("tile")),
                        },
                        score_state=self.score_state,
                    )

        return discard_id, last_seen_discard

    def on_hand_scored(self, breakdown, payments) -> None:
        render_reveal(
            self.env,
            breakdown=breakdown,
            payments=payments,
            base_points=getattr(self.env.rules, "base_points", None),
            tai_points=getattr(self.env.rules, "tai_points", None),
            totals=list(self.totals),
        )

    def on_hand_complete(self, hand_idx: int) -> None:
        # No progress bar in UI mode.
        return None


class _HeadlessDemoRunner(_BaseDemoRunner):
    provides_ui = False

    def __init__(
        self,
        *,
        seed=None,
        human_pid: Optional[int] = None,
        bot: str = "auto",
        hands: int = 1,
        jangs: int = 0,
        start_points: int = 1000,
        log_dir: Optional[str] = None,
        emit_logs: bool = True,
        hand_progress_cb: Optional[Callable[[int], None]] = None,
    ) -> None:
        super().__init__(
            seed=seed,
            human_pid=human_pid,
            bot=bot,
            hands=hands,
            jangs=jangs,
            start_points=start_points,
            log_dir=log_dir,
            emit_logs=emit_logs,
        )
        self.progress = None
        self.progress_task = None
        self.hand_progress_cb = hand_progress_cb

    def run(self) -> None:
        manager = self._build_progress_manager() if self.emit_logs else nullcontext()
        with manager as progress:
            self.progress = progress
            if self.emit_logs and progress is not None:
                total = self.max_hands if (self.max_hands is not None and self.max_hands > 0) else None
                self.progress_task = progress.add_task("Hands", total=total)
            if self.emit_logs:
                print("=== mahjong16 demo（Headless） ===")
            self.on_session_start()
            return self._execute()

    def _build_progress_manager(self):
        if self.max_hands is not None and self.max_hands > 0:
            return Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            )
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("{task.completed} hands"),
            TimeElapsedColumn(),
        )

    def on_session_start(self) -> None:
        # Headless mode does not need additional setup messages.
        return None

    def on_hand_start(self, hand_idx: int) -> None:
        # No per-hand banner in headless mode.
        return None

    def after_step(
        self,
        *,
        obs: Dict[str, Any],
        info: Optional[Dict[str, Any]],
        discard_id: int,
        last_seen_discard: Optional[tuple],
        act: Dict[str, Any],
        action_type: str,
        acting_pid: Optional[int],
        discarded_tile,
    ) -> tuple[int, Optional[tuple]]:
        # Headless mode does not render step-by-step updates.
        return discard_id, last_seen_discard

    def on_hand_scored(self, breakdown, payments) -> None:
        # Headless mode skips reveal rendering.
        return None

    def on_hand_complete(self, hand_idx: int) -> None:
        if self.emit_logs and self.progress is not None and self.progress_task is not None:
            self.progress.advance(self.progress_task, 1)
        if self.hand_progress_cb is not None:
            self.hand_progress_cb(hand_idx)


def run_demo_ui(
    seed=None,
    human_pid: Optional[int] = 0,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
):
    """Run the Mahjong16 demo with the interactive console UI enabled."""
    runner = _UIDemoRunner(
        seed=seed,
        human_pid=human_pid,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=log_dir,
    )
    runner.run()


def run_demo_headless(
    seed=None,
    human_pid: Optional[int] = None,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
):
    """Run the Mahjong16 demo without the console UI (headless)."""
    runner = _HeadlessDemoRunner(
        seed=seed,
        human_pid=None,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=log_dir,
    )
    runner.run()


def run_demo_headless_collect(
    seed=None,
    human_pid: Optional[int] = None,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
    hand_progress_cb: Optional[Callable[[int], None]] = None,
):
    """Run the headless demo and return per-hand summaries without writing logs."""
    runner = _HeadlessDemoRunner(
        seed=seed,
        human_pid=human_pid,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=log_dir,
        emit_logs=False,
        hand_progress_cb=hand_progress_cb,
    )
    return runner.run()


def run_demo(
    seed=None,
    human_pid: Optional[int] = 0,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
    enable_ui: bool = True,
):
    """Backward-compatible wrapper for existing callers.

    Prefer using `run_demo_ui` or `run_demo_headless` when the desired mode is known.
    """
    if enable_ui:
        return run_demo_ui(
            seed=seed,
            human_pid=human_pid,
            bot=bot,
            hands=hands,
            jangs=jangs,
            start_points=start_points,
            log_dir=log_dir,
        )
    return run_demo_headless(
        seed=seed,
        human_pid=None,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=log_dir,
    )


def run_demo_headless_batch(
    *,
    sessions: int,
    cores: Optional[int] = None,
    seed: Optional[int] = None,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
    emit_logs: bool = True,
) -> List[Dict[str, Any]]:
    """Run multiple headless demo sessions, optionally in parallel, and aggregate logs."""

    if sessions <= 0:
        raise ValueError("sessions must be >= 1")
    if cores is not None and cores <= 0:
        raise ValueError("cores must be >= 1 when provided")

    max_workers = cores if cores is not None else min(sessions, os.cpu_count() or 1)
    max_workers = max(1, min(max_workers, sessions))
    session_seeds = _prepare_session_seeds(seed, sessions)

    results: List[Tuple[int, Optional[int], List[Dict[str, Any]]]] = []
    jobs = list(enumerate(session_seeds))

    collapse_sessions = emit_logs and sessions > 8

    progress_manager = (
        Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )
        if emit_logs and sessions > 1
        else nullcontext()
    )

    with progress_manager as progress:
        session_tasks: Dict[int, int] = {}
        aggregate_task_id: Optional[int] = None

        def _log(message: str) -> None:
            if not emit_logs:
                return
            if progress is not None:
                progress.console.print(message)
            else:
                print(message)

        def _update_session(idx: int, hand_idx: int) -> None:
            if progress is None or collapse_sessions:
                return
            task_id = session_tasks.get(idx)
            if task_id is None:
                return
            progress.update(task_id, completed=hand_idx)

        def _finish_session(idx: int, hand_count: int) -> None:
            if progress is None:
                return
            if collapse_sessions and aggregate_task_id is not None:
                progress.advance(aggregate_task_id)
                task = progress.tasks[aggregate_task_id]
                if task.total is not None and task.completed >= task.total:
                    progress.stop_task(aggregate_task_id)
                return
            task_id = session_tasks.get(idx)
            if task_id is None:
                return
            task = progress.tasks[task_id]
            target = hand_count
            if task.total is not None:
                target = min(hand_count, task.total)
            progress.update(task_id, completed=target)
            progress.stop_task(task_id)

        def _make_hand_cb(idx: int) -> Optional[Callable[[int], None]]:
            if progress is None or collapse_sessions:
                return None
            task_id = session_tasks.get(idx)
            if task_id is None:
                return None

            def _cb(hand_idx: int) -> None:
                progress.update(task_id, completed=hand_idx)

            return _cb

        if emit_logs:
            _log("=== mahjong16 demo batch（Headless） ===")

        if progress is not None:
            if collapse_sessions:
                aggregate_task_id = progress.add_task(
                    "Sessions Completed",
                    total=sessions,
                )
            else:
                per_session_total = None
                if jangs > 0:
                    per_session_total = None
                elif hands > 0:
                    per_session_total = hands
                for idx, _ in jobs:
                    session_tasks[idx] = progress.add_task(
                        f"Session {idx + 1}",
                        total=per_session_total,
                    )

        if max_workers <= 1:
            for idx, session_seed in jobs:
                hand_cb = _make_hand_cb(idx)
                summaries = run_demo_headless_collect(
                    seed=session_seed,
                    human_pid=None,
                    bot=bot,
                    hands=hands,
                    jangs=jangs,
                    start_points=start_points,
                    log_dir=None,
                    hand_progress_cb=hand_cb,
                )
                results.append((idx, session_seed, summaries))
                _finish_session(idx, len(summaries))
        else:
            manager = mp.Manager() if progress is not None else None
            progress_queue = manager.Queue() if manager is not None else None

            try:
                with ProcessPoolExecutor(max_workers=max_workers) as pool:
                    future_map = {
                        pool.submit(
                            _run_headless_batch_session,
                            idx,
                            session_seed,
                            bot,
                            hands,
                            jangs,
                            start_points,
                            progress_queue,
                        ): idx
                        for idx, session_seed in jobs
                    }

                    pending = set(future_map.keys())
                    while pending:
                        if progress_queue is not None:
                            try:
                                session_idx, hand_idx = progress_queue.get(timeout=0.1)
                            except Empty:
                                pass
                            else:
                                _update_session(session_idx, hand_idx)

                        done = [f for f in pending if f.done()]
                        for fut in done:
                            pending.remove(fut)
                            idx, session_seed, summaries = fut.result()
                            results.append((idx, session_seed, summaries))
                            _finish_session(idx, len(summaries))

                    if progress_queue is not None:
                        while True:
                            try:
                                session_idx, hand_idx = progress_queue.get_nowait()
                            except Empty:
                                break
                            else:
                                _update_session(session_idx, hand_idx)
            finally:
                if manager is not None:
                    manager.shutdown()

    results.sort(key=lambda item: item[0])
    all_summaries: List[Dict[str, Any]] = []
    global_hand_index = 1
    for session_idx, session_seed, summaries in results:
        for local_idx, summary in enumerate(summaries, start=1):
            entry = dict(summary)
            entry.setdefault("hand_index", local_idx)
            entry["session_index"] = session_idx
            entry["session_hand_index"] = local_idx
            entry["global_hand_index"] = global_hand_index
            entry["session_seed"] = session_seed
            all_summaries.append(entry)
            global_hand_index += 1

    if emit_logs:
        _finalize_demo(all_summaries, log_dir=log_dir, enable_ui=False)
    elif log_dir is not None:
        write_hand_log(all_summaries, log_dir)

    return all_summaries


def _finalize_demo(
    hand_summaries: list,
    log_dir: Optional[str] = None,
    enable_ui: bool = True,
) -> None:
    """Render post-session summaries, optionally dump logs, and finish the demo."""
    if enable_ui and hand_summaries:
        render_winners_summary(hand_summaries)

    if log_dir is not None:
        try:
            written = write_hand_log(hand_summaries, log_dir)
            if written is not None:
                print(f"[log] wrote per-hand summary to {written}")
        except Exception as exc:  # pragma: no cover - defensive logging path
            print(f"[warn] failed to write log in {log_dir}: {exc}")

    print("=== demo finished ===")


def _prepare_session_seeds(base_seed: Optional[int], sessions: int) -> List[Optional[int]]:
    if base_seed is None:
        rng = random.SystemRandom()
        return [rng.randrange(2**31) for _ in range(sessions)]

    seeds: List[Optional[int]] = [int(base_seed)]
    if sessions == 1:
        return seeds

    rng = random.Random(base_seed)
    for _ in range(1, sessions):
        seeds.append(rng.randrange(2**31))
    return seeds


def _run_headless_batch_session(
    session_index: int,
    session_seed: Optional[int],
    bot: str,
    hands: int,
    jangs: int,
    start_points: int,
    progress_queue=None,
) -> Tuple[int, Optional[int], List[Dict[str, Any]]]:
    def _report(hand_idx: int) -> None:
        if progress_queue is not None:
            try:
                progress_queue.put((session_index, hand_idx))
            except Exception:
                pass

    summaries = run_demo_headless_collect(
        seed=session_seed,
        human_pid=None,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=None,
        hand_progress_cb=_report if progress_queue is not None else None,
    )
    return session_index, session_seed, summaries
