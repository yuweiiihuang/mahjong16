from __future__ import annotations

import multiprocessing as mp
import os
import random
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from queue import Empty
from typing import Any, Callable, Dict, List, Optional, Tuple

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from domain import Mahjong16Env, Ruleset
from domain.scoring.tables import load_scoring_assets
from domain.scoring.types import ScoringTable

from app.logging import HandLogWriter, write_hand_log
from app.strategies import Strategy, build_strategies
from app.table import TableManager
from application.session_service import SessionService
from interfaces.console.ui_adapter import ConsoleUIAdapter
from interfaces.headless.log_adapter import HeadlessLogAdapter
from ui.console import render_winners_summary


def _build_session_dependencies(
    seed: Optional[int],
    human_pid: Optional[int],
    bot: str,
) -> Tuple[Mahjong16Env, TableManager, List[Strategy], ScoringTable]:
    rules = Ruleset(
        scoring_profile="taiwan_base",
        rule_profile="common",
    )
    env = Mahjong16Env(rules, seed=seed)
    table_manager = TableManager(rules, seed=seed)
    strategies = build_strategies(env.rules.n_players, human_pid, bot)
    scoring_table = load_scoring_assets(rules.scoring_profile, rules.scoring_overrides_path)
    return env, table_manager, strategies, scoring_table


def build_ui_session(
    *,
    seed: Optional[int] = None,
    human_pid: Optional[int] = 0,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
    emit_logs: bool = True,
) -> SessionService:
    """Assemble a UI session service with the rich console adapter."""

    env, table_manager, strategies, scoring_table = _build_session_dependencies(seed, human_pid, bot)
    adapter = ConsoleUIAdapter(
        human_pid=human_pid,
        n_players=env.rules.n_players,
        log_dir=log_dir,
        emit_logs=emit_logs,
    )
    return SessionService(
        env=env,
        table_manager=table_manager,
        strategies=strategies,
        scoring_assets=scoring_table,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        table_view_port=adapter,
        hand_summary_port=adapter,
    )


def build_headless_session(
    *,
    seed: Optional[int] = None,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
    emit_logs: bool = True,
    hand_progress_cb: Optional[Callable[[int], None]] = None,
) -> SessionService:
    """Assemble a headless session service with logging/progress adapters."""

    env, table_manager, strategies, scoring_table = _build_session_dependencies(seed, None, bot)
    adapter = HeadlessLogAdapter(
        n_players=env.rules.n_players,
        log_dir=log_dir,
        emit_logs=emit_logs,
        hand_progress_cb=hand_progress_cb,
    )
    return SessionService(
        env=env,
        table_manager=table_manager,
        strategies=strategies,
        scoring_assets=scoring_table,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        hand_summary_port=adapter,
        progress_port=adapter,
    )


def run_demo_ui(
    seed=None,
    human_pid: Optional[int] = 0,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
) -> None:
    """Run the Mahjong16 demo with the interactive console UI enabled."""

    session = build_ui_session(
        seed=seed,
        human_pid=human_pid,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=log_dir,
    )
    session.run()


def run_demo_headless(
    seed=None,
    human_pid: Optional[int] = None,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
    emit_logs: bool = True,
) -> None:
    """Run the Mahjong16 demo without the console UI (headless)."""

    session = build_headless_session(
        seed=seed,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=log_dir,
        emit_logs=emit_logs,
    )
    session.run()


def run_demo_headless_collect(
    seed=None,
    human_pid: Optional[int] = None,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    log_dir: Optional[str] = None,
    hand_progress_cb: Optional[Callable[[int], None]] = None,
) -> List[Dict[str, Any]]:
    """Run the headless demo and return per-hand summaries without writing logs."""

    session = build_headless_session(
        seed=seed,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=log_dir,
        emit_logs=False,
        hand_progress_cb=hand_progress_cb,
    )
    return session.run()


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
    """Backward-compatible wrapper for existing callers."""

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

    jobs = list(enumerate(session_seeds))

    collapse_sessions = emit_logs and sessions > 8

    batch_log_writer: Optional[HandLogWriter] = None
    batch_log_path = None
    batch_log_failed = False

    def _append_batch_log(summary: Dict[str, Any]) -> None:
        nonlocal batch_log_writer, batch_log_path, batch_log_failed
        if log_dir is None or batch_log_failed:
            return
        try:
            if batch_log_writer is None:
                payments = summary.get("payments") or []
                totals = summary.get("totals_after_hand") or []
                max_players = max(len(payments), len(totals)) or None
                batch_log_writer = HandLogWriter(
                    log_dir,
                    max_players=max_players,
                )
            batch_log_writer.append(summary)
            if batch_log_path is None:
                batch_log_path = batch_log_writer.path
        except Exception as exc:
            batch_log_failed = True
            batch_log_writer = None
            if emit_logs:
                print(f"[warn] failed to append batch log in {log_dir}: {exc}")

    pending_results: Dict[int, Tuple[Optional[int], List[Dict[str, Any]]]] = {}
    next_flush_session = 0
    all_summaries: List[Dict[str, Any]] = []
    global_hand_index = 1

    def _flush_ready_sessions() -> None:
        nonlocal next_flush_session, global_hand_index
        while next_flush_session in pending_results:
            session_seed, summaries = pending_results.pop(next_flush_session)
            for local_idx, summary in enumerate(summaries, start=1):
                entry = dict(summary)
                entry.setdefault("hand_index", local_idx)
                entry["session_index"] = next_flush_session
                entry["session_hand_index"] = local_idx
                entry["global_hand_index"] = global_hand_index
                entry["session_seed"] = session_seed
                all_summaries.append(entry)
                global_hand_index += 1
                _append_batch_log(entry)
            next_flush_session += 1

    def _record_session(idx: int, session_seed: Optional[int], summaries: List[Dict[str, Any]]) -> None:
        pending_results[idx] = (session_seed, summaries)
        _flush_ready_sessions()

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
                _record_session(idx, session_seed, summaries)
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
                            _record_session(idx, session_seed, summaries)
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

    _flush_ready_sessions()

    if batch_log_writer is not None:
        batch_log_writer.close()

    finalize_log_dir = log_dir
    if batch_log_failed:
        finalize_log_dir = log_dir
    elif batch_log_writer is not None:
        finalize_log_dir = None

    if emit_logs:
        _finalize_demo(all_summaries, log_dir=finalize_log_dir, enable_ui=False)
        if batch_log_writer is not None and batch_log_path is not None:
            print(f"[log] appended per-hand summary to {batch_log_path}")
    elif log_dir is not None and (batch_log_writer is None or batch_log_failed):
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
