from __future__ import annotations

import multiprocessing as mp
import os
import random
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from queue import Empty
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

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
from domain.scoring.engine import compute_payments, score_with_breakdown
from domain.scoring.lookup import load_scoring_assets
from domain.scoring.score_types import ScoringContext, ScoringTable
from domain.tiles import tile_sort_key

from app.logging import HandLogWriter, write_hand_log
from app.table import TableManager
from app.session.adapters import ConsoleUIAdapter, HeadlessLogAdapter
from app.session.ports import (
    HandSummaryPort,
    ProgressPort,
    ScoreState,
    StepEvent,
    TableViewPort,
)
from bots import Strategy, build_strategies
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


class SessionService:
    """High level orchestration for Mahjong16 demo sessions."""

    def __init__(
        self,
        *,
        env: Mahjong16Env,
        table_manager: TableManager,
        strategies: Sequence[Strategy],
        scoring_assets: ScoringTable,
        hands: int = 1,
        jangs: Optional[int] = 0,
        start_points: int = 1000,
        table_view_port: Optional[TableViewPort] = None,
        hand_summary_port: Optional[HandSummaryPort] = None,
        progress_port: Optional[ProgressPort] = None,
    ) -> None:
        self.env = env
        self.table_manager = table_manager
        self.strategies = list(strategies)
        self.scoring_assets = scoring_assets
        self.n_players = self.env.rules.n_players

        self.table_manager.initialize(self.n_players)

        normalized_points = self._normalize_start_points(start_points)
        self.totals = [normalized_points for _ in range(self.n_players)]
        self.hand_delta = [0 for _ in range(self.n_players)]
        self.score_state: ScoreState = {
            "totals": self.totals,
            "deltas": self.hand_delta,
        }

        self.target_jangs = self._normalize_jangs(jangs)
        self.play_until_negative = hands == -1 and self.target_jangs is None
        if self.play_until_negative or self.target_jangs is not None:
            self.max_hands: Optional[int] = None
        else:
            self.max_hands = hands if hands > 0 else 0

        self.table_view_port = table_view_port
        self.hand_summary_port = hand_summary_port
        self.progress_port = progress_port

        self.hand_summaries: List[Dict[str, Any]] = []

        self._session_started = False
        self._session_finalized = False

    def run(self) -> List[Dict[str, Any]]:
        """Execute a complete demo session and return per-hand summaries."""

        self._notify_session_start()
        hand_idx = 0
        try:
            while True:
                if self.max_hands is not None and hand_idx >= self.max_hands:
                    break

                hand_idx += 1
                obs = self.table_manager.start_hand(self.env)
                self.hand_delta = [0 for _ in range(self.n_players)]
                self.score_state["deltas"] = self.hand_delta

                if getattr(self.env, "done", False):
                    if self._process_hand_end(hand_idx):
                        break
                    continue

                if self.table_view_port is not None:
                    jang_index = getattr(self.table_manager.state, "jang_count", 0) + 1
                    self.table_view_port.on_hand_start(
                        hand_index=hand_idx,
                        jang_index=jang_index,
                        env=self.env,
                        score_state=self.score_state,
                    )

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
                                return self.hand_summaries
                            break
                        else:
                            raise AssertionError(
                                f"No legal actions available for player {obs.get('player')} in phase {obs.get('phase')}"
                            )

                    strategy = self.strategies[obs.get("player")]
                    act = strategy.choose(obs)
                    action_type = (act.get("type") or "").upper()
                    acting_pid = obs.get("player")
                    discarded_tile = act.get("tile") if action_type == "DISCARD" else None

                    obs, _reward, done, info = self.env.step(act)

                    if self.table_view_port is not None:
                        event = StepEvent(
                            observation=obs,
                            info=info,
                            action=act,
                            acting_pid=acting_pid,
                            action_type=action_type,
                            discarded_tile=discarded_tile,
                        )
                        self.table_view_port.on_step(
                            event=event,
                            env=self.env,
                            score_state=self.score_state,
                        )

                    if done:
                        if self._process_hand_end(hand_idx):
                            return self.hand_summaries
                        break

                if self.play_until_negative and any(pt < 0 for pt in self.totals):
                    break

            return self.hand_summaries
        finally:
            self._notify_session_end()

    def _process_hand_end(self, hand_idx: int) -> bool:
        ctx = ScoringContext.from_env(self.env, self.scoring_assets)
        rewards, breakdown = score_with_breakdown(ctx)
        payments_raw, _ = compute_payments(
            ctx,
            getattr(self.env.rules, "base_points", 100),
            getattr(self.env.rules, "tai_points", 20),
            rewards=rewards,
            breakdown=breakdown,
        )

        payments = [0 for _ in range(self.n_players)]
        for pid in range(self.n_players):
            try:
                delta = int(payments_raw[pid])
            except Exception:
                delta = 0
            payments[pid] = delta
            self.totals[pid] += delta
            self.hand_delta[pid] = delta

        if self.table_view_port is not None:
            self.table_view_port.on_hand_scored(
                hand_index=hand_idx,
                breakdown=breakdown,
                payments=payments,
                env=self.env,
                score_state=self.score_state,
            )

        summary = self._build_summary(hand_idx, breakdown, payments, ctx)
        self.hand_summaries.append(summary)
        if self.hand_summary_port is not None:
            self.hand_summary_port.on_hand_summary(summary)

        self.table_manager.finish_hand(self.env)

        if self.progress_port is not None:
            self.progress_port.on_hand_complete(hand_idx)

        if self.target_jangs is not None:
            jang_count = getattr(self.table_manager.state, "jang_count", 0)
            if jang_count >= self.target_jangs:
                return True

        return False

    def _build_summary(
        self,
        hand_idx: int,
        breakdown: Dict[int, List[Dict[str, Any]]],
        payments: List[int],
        ctx: ScoringContext,
    ) -> Dict[str, Any]:
        winner = getattr(self.env, "winner", None)
        summary: Dict[str, Any]
        if winner is not None:
            try:
                player = self.env.players[winner]
                if isinstance(player, dict):
                    get = player.get
                    hand_tiles = sorted(list(get("hand") or []), key=tile_sort_key)
                    melds = [m if isinstance(m, dict) else {} for m in (get("melds") or [])]
                    flowers = sorted(list(get("flowers") or []), key=tile_sort_key)
                else:
                    hand_tiles = []
                    melds = []
                    flowers = []
                win_source = (getattr(self.env, "win_source", None) or "").upper()
                ron_from = getattr(self.env, "turn_at_win", None) if win_source == "RON" else None
                win_tile = getattr(self.env, "win_tile", None)
                dealer_pid = getattr(self.env, "dealer_pid", None)
                seat_winds = getattr(self.env, "seat_winds", None)
                dealer_wind = None
                winner_wind = None
                if isinstance(seat_winds, list):
                    if isinstance(dealer_pid, int) and 0 <= dealer_pid < len(seat_winds):
                        dealer_wind = seat_winds[dealer_pid]
                    if 0 <= winner < len(seat_winds):
                        winner_wind = seat_winds[winner]
            except Exception:
                hand_tiles = []
                melds = []
                flowers = []
                win_source = (getattr(self.env, "win_source", None) or "").upper()
                ron_from = getattr(self.env, "turn_at_win", None) if win_source == "RON" else None
                win_tile = getattr(self.env, "win_tile", None)
                dealer_pid = getattr(self.env, "dealer_pid", None)
                dealer_wind = None
                winner_wind = None

            summary = {
                "hand_index": hand_idx,
                "jang_index": getattr(self.table_manager.state, "jang_count", 0) + 1,
                "winner": winner,
                "win_source": win_source,
                "ron_from": ron_from,
                "win_tile": win_tile,
                "hand": hand_tiles,
                "melds": melds,
                "flowers": flowers,
                "breakdown": list(breakdown.get(winner, [])),
                "payments": list(payments),
                "base_points": getattr(self.env.rules, "base_points", None),
                "tai_points": getattr(self.env.rules, "tai_points", None),
                "quan_feng": getattr(self.env, "quan_feng", None),
                "dealer_pid": dealer_pid,
                "dealer_wind": dealer_wind,
                "winner_wind": winner_wind,
                "totals_after_hand": list(self.totals),
                "remain_tiles": ctx.wall_len,
            }
        else:
            dealer_pid = getattr(self.env, "dealer_pid", None)
            seat_winds = getattr(self.env, "seat_winds", None)
            dealer_wind = None
            if isinstance(dealer_pid, int) and isinstance(seat_winds, list) and 0 <= dealer_pid < len(seat_winds):
                dealer_wind = seat_winds[dealer_pid]
            summary = {
                "hand_index": hand_idx,
                "jang_index": getattr(self.table_manager.state, "jang_count", 0) + 1,
                "winner": None,
                "result": "DRAW",
                "payments": list(payments),
                "base_points": getattr(self.env.rules, "base_points", None),
                "tai_points": getattr(self.env.rules, "tai_points", None),
                "quan_feng": getattr(self.env, "quan_feng", None),
                "dealer_pid": dealer_pid,
                "dealer_wind": dealer_wind,
                "totals_after_hand": list(self.totals),
                "remain_tiles": ctx.wall_len,
            }

        return summary

    def _notify_session_start(self) -> None:
        if self._session_started:
            return
        self._session_started = True
        if self.table_view_port is not None:
            self.table_view_port.on_session_start(env=self.env, score_state=self.score_state)
        if self.progress_port is not None:
            self.progress_port.on_session_start(self.max_hands)

    def _notify_session_end(self) -> None:
        if self._session_finalized:
            return
        self._session_finalized = True
        if self.hand_summary_port is not None:
            self.hand_summary_port.finalize(self.hand_summaries)
        if self.table_view_port is not None:
            self.table_view_port.on_session_end(
                summaries=self.hand_summaries,
                env=self.env,
                score_state=self.score_state,
            )
        if self.progress_port is not None:
            self.progress_port.on_session_end()

    @staticmethod
    def _normalize_start_points(start_points: int) -> int:
        try:
            value = int(start_points)
        except Exception:
            value = 1000
        if value <= 0:
            value = 1
        return value

    @staticmethod
    def _normalize_jangs(jangs: Optional[int]) -> Optional[int]:
        if jangs is None:
            return None
        try:
            value = int(jangs)
        except Exception:
            return None
        if value <= 0:
            return None
        return value


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
