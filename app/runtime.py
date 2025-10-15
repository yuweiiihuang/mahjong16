from __future__ import annotations

import logging
import multiprocessing as mp
import os
import random
import time
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
from app.session.adapters.web_frontend import WebFrontendAdapter
from app.session.ports import (
    HandSummaryPort,
    ProgressPort,
    ScoreState,
    StepEvent,
    TableViewPort,
)
from bots import Strategy, build_strategies
from ui.console import render_winners_summary
from ui.web.bridge import WebSessionBridge
from ui.web.server import run_web_app
from ui.web.strategy import WebHumanStrategy


logger = logging.getLogger(__name__)


def _is_indexable_sequence(collection: Any, index: int) -> bool:
    return (
        isinstance(collection, Sequence)
        and not isinstance(collection, (str, bytes))
        and isinstance(index, int)
        and 0 <= index < len(collection)
    )


def _coerce_sequence(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _resolve_player_field(player: Any, field: str) -> Any:
    if isinstance(player, dict):
        return player.get(field)
    return getattr(player, field, None)


def _extract_sorted_tiles(values: Any) -> List[int]:
    tiles = []
    for tile in _coerce_sequence(values):
        try:
            tiles.append(int(tile))
        except (TypeError, ValueError):
            continue
    return sorted(tiles, key=tile_sort_key)


def _normalize_melds(values: Any) -> List[Dict[str, Any]]:
    melds: List[Dict[str, Any]] = []
    for meld in _coerce_sequence(values):
        if isinstance(meld, dict):
            melds.append(meld)
            continue
        to_dict = getattr(meld, "to_dict", None)
        if callable(to_dict):
            try:
                meld_dict = to_dict()
            except Exception:  # pragma: no cover - defensive path
                logger.debug("Skipping meld %r because to_dict() raised an exception", meld)
                meld_dict = {}
            if isinstance(meld_dict, dict):
                melds.append(meld_dict)
                continue
        attributes = getattr(meld, "__dict__", None)
        if isinstance(attributes, dict):
            melds.append(dict(attributes))
        else:
            melds.append({})
    return melds


def _extract_winner_assets(env: Mahjong16Env, winner: int) -> Tuple[List[int], List[Dict[str, Any]], List[int]]:
    players = getattr(env, "players", None)
    if not _is_indexable_sequence(players, winner):
        return [], [], []
    player = players[winner]
    hand_tiles = _extract_sorted_tiles(_resolve_player_field(player, "hand"))
    melds = _normalize_melds(_resolve_player_field(player, "melds"))
    flowers = _extract_sorted_tiles(_resolve_player_field(player, "flowers"))
    return hand_tiles, melds, flowers


def _resolve_winds(
    seat_winds: Any,
    dealer_pid: Optional[int],
    winner: Optional[int],
) -> Tuple[Optional[Any], Optional[Any]]:
    dealer_wind = None
    winner_wind = None
    if isinstance(seat_winds, Sequence) and not isinstance(seat_winds, (str, bytes)):
        if isinstance(dealer_pid, int) and 0 <= dealer_pid < len(seat_winds):
            dealer_wind = seat_winds[dealer_pid]
        if isinstance(winner, int) and 0 <= winner < len(seat_winds):
            winner_wind = seat_winds[winner]
    return dealer_wind, winner_wind


def _build_session_dependencies(
    seed: Optional[int],
    human_pid: Optional[int],
    bot: str,
    *,
    bot_delay: float = 2.0,
    human_strategy_factory: Optional[Callable[[], Strategy]] = None,
) -> Tuple[Mahjong16Env, TableManager, List[Strategy], ScoringTable]:
    rules = Ruleset(
        scoring_profile="taiwan_base",
        rule_profile="common",
    )
    env = Mahjong16Env(rules, seed=seed)
    table_manager = TableManager(rules, seed=seed)
    strategies = build_strategies(
        env.rules.n_players,
        human_pid,
        bot,
        bot_delay=bot_delay,
        human_factory=human_strategy_factory,
    )
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
            while self._has_more_hands(hand_idx):
                hand_idx += 1
                session_complete = self._play_single_hand(hand_idx)
                if session_complete or self._should_stop_after_hand():
                    break

            return self.hand_summaries
        finally:
            self._notify_session_end()

    def _has_more_hands(self, hand_idx: int) -> bool:
        return self.max_hands is None or hand_idx < self.max_hands

    def _play_single_hand(self, hand_idx: int) -> bool:
        obs = self._prepare_hand_state()
        if getattr(self.env, "done", False):
            return self._process_hand_end(hand_idx)

        self._emit_hand_start(hand_idx)
        return self._play_hand_loop(hand_idx, obs)

    def _prepare_hand_state(self) -> Dict[str, Any]:
        obs = self.table_manager.start_hand(self.env)
        self.hand_delta = [0 for _ in range(self.n_players)]
        self.score_state["deltas"] = self.hand_delta
        return obs

    def _current_jang_index(self) -> int:
        return getattr(self.table_manager.state, "jang_count", 0) + 1

    def _emit_hand_start(self, hand_idx: int) -> None:
        if self.table_view_port is None:
            return
        self.table_view_port.on_hand_start(
            hand_index=hand_idx,
            jang_index=self._current_jang_index(),
            env=self.env,
            score_state=self.score_state,
        )

    def _play_hand_loop(self, hand_idx: int, obs: Dict[str, Any]) -> bool:
        while True:
            obs, session_complete = self._resolve_actions(obs, hand_idx)
            if obs is None:
                return session_complete

            strategy = self.strategies[obs.get("player")]
            act = strategy.choose(obs)
            action_type = (act.get("type") or "").upper()
            acting_pid = obs.get("player")
            discarded_tile = act.get("tile") if action_type == "DISCARD" else None

            delay = self._strategy_delay(strategy, act, obs, action_type)
            if delay > 0:
                time.sleep(delay)

            obs, done = self._step_environment(
                act,
                action_type=action_type,
                acting_pid=acting_pid,
                discarded_tile=discarded_tile,
            )

            if done:
                return self._process_hand_end(hand_idx)

    def _resolve_actions(
        self,
        obs: Dict[str, Any],
        hand_idx: int,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        acts_current = obs.get("legal_actions") or []
        if acts_current:
            return obs, False

        recalculated = self.env.legal_actions()
        if recalculated:
            refreshed = dict(obs)
            refreshed["legal_actions"] = recalculated
            return refreshed, False

        if getattr(self.env, "done", False):
            return None, self._process_hand_end(hand_idx)

        raise AssertionError(
            f"No legal actions available for player {obs.get('player')} in phase {obs.get('phase')}"
        )

    def _step_environment(
        self,
        act: Dict[str, Any],
        *,
        action_type: str,
        acting_pid: Optional[int],
        discarded_tile: Optional[int],
    ) -> Tuple[Dict[str, Any], bool]:
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

        return obs, done

    def _strategy_delay(
        self,
        strategy: Strategy,
        action: Dict[str, Any],
        obs: Dict[str, Any],
        action_type: str,
    ) -> float:
        delay_fn = getattr(strategy, "delay_for", None)
        if callable(delay_fn):
            try:
                value = float(delay_fn(action, obs))
            except (TypeError, ValueError):
                return 0.0
            return value if value > 0 else 0.0
        if action_type != "DISCARD":
            return 0.0
        delay_attr = getattr(strategy, "discard_delay", 0.0)
        try:
            delay = float(delay_attr)
        except (TypeError, ValueError):
            return 0.0
        return delay if delay > 0 else 0.0

    def _should_stop_after_hand(self) -> bool:
        return self.play_until_negative and any(pt < 0 for pt in self.totals)

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
            raw_delta = payments_raw[pid] if pid < len(payments_raw) else 0
            try:
                delta = int(raw_delta)
            except (TypeError, ValueError):
                logger.error("Invalid payment value for player %s: %r; defaulting to 0", pid, raw_delta)
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
        dealer_pid = getattr(self.env, "dealer_pid", None)
        seat_winds = getattr(self.env, "seat_winds", None)

        base_summary: Dict[str, Any] = {
            "hand_index": hand_idx,
            "jang_index": self._current_jang_index(),
            "payments": list(payments),
            "base_points": getattr(self.env.rules, "base_points", None),
            "tai_points": getattr(self.env.rules, "tai_points", None),
            "quan_feng": getattr(self.env, "quan_feng", None),
            "dealer_pid": dealer_pid,
            "totals_after_hand": list(self.totals),
            "remain_tiles": ctx.wall_len,
        }

        if winner is not None:
            win_source = (getattr(self.env, "win_source", None) or "").upper()
            ron_from = getattr(self.env, "turn_at_win", None) if win_source == "RON" else None
            win_tile = getattr(self.env, "win_tile", None)
            hand_tiles, melds, flowers = _extract_winner_assets(self.env, winner)
            dealer_wind, winner_wind = _resolve_winds(seat_winds, dealer_pid, winner)
            summary = {
                **base_summary,
                "winner": winner,
                "win_source": win_source,
                "ron_from": ron_from,
                "win_tile": win_tile,
                "hand": hand_tiles,
                "melds": melds,
                "flowers": flowers,
                "breakdown": list(breakdown.get(winner, [])),
                "dealer_wind": dealer_wind,
                "winner_wind": winner_wind,
            }
        else:
            dealer_wind, _ = _resolve_winds(seat_winds, dealer_pid, None)
            summary = {
                **base_summary,
                "winner": None,
                "result": "DRAW",
                "dealer_wind": dealer_wind,
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


def build_web_session(
    *,
    seed: Optional[int] = None,
    human_pid: Optional[int] = 0,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
) -> Tuple[SessionService, WebSessionBridge]:
    """Assemble a session service configured for the web frontend."""

    bridge = WebSessionBridge()
    env, table_manager, strategies, scoring_table = _build_session_dependencies(
        seed,
        human_pid,
        bot,
        human_strategy_factory=lambda: WebHumanStrategy(bridge),
    )
    adapter = WebFrontendAdapter(
        bridge=bridge,
        human_pid=human_pid,
        n_players=env.rules.n_players,
    )
    session = SessionService(
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
    return session, bridge


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

    env, table_manager, strategies, scoring_table = _build_session_dependencies(
        seed,
        None,
        bot,
        bot_delay=0.0,
    )
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


def run_demo_web(
    seed=None,
    human_pid: Optional[int] = 0,
    bot: str = "auto",
    hands: int = 1,
    jangs: int = 0,
    start_points: int = 1000,
    *,
    host: str = "0.0.0.0",
    port: int = 8000,
    log_level: str = "info",
) -> None:
    """Run the Mahjong16 demo with the interactive web UI enabled."""

    session, bridge = build_web_session(
        seed=seed,
        human_pid=human_pid,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
    )
    run_web_app(session=session, bridge=bridge, host=host, port=port, log_level=log_level)


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


class BatchLogManager:
    """Manage incremental batch log writes and fallbacks."""

    def __init__(self, log_dir: Optional[str], emit_logs: bool) -> None:
        self.log_dir = log_dir
        self.emit_logs = emit_logs
        self._writer: Optional[HandLogWriter] = None
        self._log_path: Optional[str] = None
        self._failed = False
        self._had_writer = False

    def append(self, summary: Dict[str, Any], log_fn: Optional[Callable[[str], None]] = None) -> None:
        if self.log_dir is None or self._failed:
            return
        try:
            if self._writer is None:
                payments = summary.get("payments") or []
                totals = summary.get("totals_after_hand") or []
                max_players = max(len(payments), len(totals)) or None
                self._writer = HandLogWriter(
                    self.log_dir,
                    max_players=max_players,
                )
                self._had_writer = True
            self._writer.append(summary)
            if self._log_path is None and self._writer.path is not None:
                self._log_path = str(self._writer.path)
        except Exception as exc:
            self._failed = True
            if self._writer is not None:
                try:
                    self._writer.close()
                except Exception:  # pragma: no cover - defensive cleanup
                    logger.debug("Failed to close batch log writer after append error", exc_info=True)
            self._writer = None
            self._log_path = None
            logger.exception("Failed to append batch log entry in %s", self.log_dir)
            if log_fn is not None:
                log_fn(f"[warn] failed to append batch log in {self.log_dir}: {exc}")

    def close(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
            finally:
                self._writer = None

    def finalize(
        self,
        hand_summaries: List[Dict[str, Any]],
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        self.close()
        finalize_dir = self.log_dir
        if self._had_writer and not self._failed:
            finalize_dir = None

        if not self.emit_logs and self.log_dir is not None and (not self._had_writer or self._failed):
            try:
                written = write_hand_log(hand_summaries, self.log_dir)
                if log_fn is not None and written is not None:
                    log_fn(f"[log] wrote per-hand summary to {written}")
            except Exception:
                logger.exception("Failed to write hand log in %s during batch finalize", self.log_dir)

        return finalize_dir, self._log_path if not self._failed else None


class HeadlessBatchRunner:
    """Coordinate batched headless demo runs."""

    def __init__(
        self,
        *,
        sessions: int,
        cores: Optional[int],
        seed: Optional[int],
        bot: str,
        hands: int,
        jangs: int,
        start_points: int,
        log_dir: Optional[str],
        emit_logs: bool,
    ) -> None:
        if sessions <= 0:
            raise ValueError("sessions must be >= 1")
        if cores is not None and cores <= 0:
            raise ValueError("cores must be >= 1 when provided")

        self.sessions = sessions
        self.cores = cores
        self.seed = seed
        self.bot = bot
        self.hands = hands
        self.jangs = jangs
        self.start_points = start_points
        self.emit_logs = emit_logs

        self.log_manager = BatchLogManager(log_dir, emit_logs)
        self.collapse_sessions = emit_logs and sessions > 8

        self.jobs: List[Tuple[int, Optional[int]]] = []
        self.pending_results: Dict[int, Tuple[Optional[int], List[Dict[str, Any]]]] = {}
        self.next_flush_session = 0
        self.all_summaries: List[Dict[str, Any]] = []
        self.global_hand_index = 1

        self.progress: Optional[Progress] = None
        self.session_tasks: Dict[int, int] = {}
        self.aggregate_task_id: Optional[int] = None
        self.max_workers: int = 1

    def run(self) -> List[Dict[str, Any]]:
        self.max_workers = self._determine_worker_count()
        session_seeds = _prepare_session_seeds(self.seed, self.sessions)
        self.jobs = list(enumerate(session_seeds))

        with self._progress_context() as progress:
            self._bind_progress(progress)
            if self.emit_logs:
                self._log("=== mahjong16 demo batch（Headless） ===")
            self._initialize_progress_tasks()
            if self.max_workers <= 1:
                self._run_serial_jobs()
            else:
                self._run_parallel_jobs()

        self._flush_ready_sessions()
        finalize_dir, appended_path = self.log_manager.finalize(
            self.all_summaries,
            self._log if self.emit_logs else None,
        )

        if self.emit_logs:
            _finalize_demo(self.all_summaries, log_dir=finalize_dir, enable_ui=False)
            if appended_path is not None:
                self._log(f"[log] appended per-hand summary to {appended_path}")

        return self.all_summaries

    def _determine_worker_count(self) -> int:
        if self.cores is not None:
            requested = min(self.cores, self.sessions)
            return max(1, requested)
        available = os.cpu_count() or 1
        return max(1, min(self.sessions, available))

    def _progress_context(self):
        if self.emit_logs and self.sessions > 1:
            return Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            )
        return nullcontext()

    def _bind_progress(self, progress: Any) -> None:
        self.progress = progress if isinstance(progress, Progress) else None

    def _log(self, message: str) -> None:
        if not self.emit_logs:
            return
        if self.progress is not None:
            self.progress.console.print(message)
        else:
            print(message)

    def _initialize_progress_tasks(self) -> None:
        if self.progress is None:
            return
        if self.collapse_sessions:
            self.aggregate_task_id = self.progress.add_task(
                "Sessions Completed",
                total=self.sessions,
            )
            return
        per_session_total = None
        if self.jangs <= 0 and self.hands > 0:
            per_session_total = self.hands
        for idx, _ in self.jobs:
            self.session_tasks[idx] = self.progress.add_task(
                f"Session {idx + 1}",
                total=per_session_total,
            )

    def _make_hand_callback(self, idx: int) -> Optional[Callable[[int], None]]:
        if self.progress is None or self.collapse_sessions:
            return None
        task_id = self.session_tasks.get(idx)
        if task_id is None:
            return None

        def _cb(hand_idx: int) -> None:
            self.progress.update(task_id, completed=hand_idx)

        return _cb

    def _update_session(self, idx: int, hand_idx: int) -> None:
        if self.progress is None or self.collapse_sessions:
            return
        task_id = self.session_tasks.get(idx)
        if task_id is None:
            return
        self.progress.update(task_id, completed=hand_idx)

    def _finish_session(self, idx: int, hand_count: int) -> None:
        if self.progress is None:
            return
        if self.collapse_sessions and self.aggregate_task_id is not None:
            self.progress.advance(self.aggregate_task_id)
            task = self.progress.tasks[self.aggregate_task_id]
            if task.total is not None and task.completed >= task.total:
                self.progress.stop_task(self.aggregate_task_id)
            return
        task_id = self.session_tasks.get(idx)
        if task_id is None:
            return
        task = self.progress.tasks[task_id]
        target = hand_count if task.total is None else min(hand_count, task.total)
        self.progress.update(task_id, completed=target)
        self.progress.stop_task(task_id)

    def _record_session(self, idx: int, session_seed: Optional[int], summaries: List[Dict[str, Any]]) -> None:
        self.pending_results[idx] = (session_seed, summaries)
        self._flush_ready_sessions()

    def _flush_ready_sessions(self) -> None:
        while self.next_flush_session in self.pending_results:
            session_seed, summaries = self.pending_results.pop(self.next_flush_session)
            for local_idx, summary in enumerate(summaries, start=1):
                entry = dict(summary)
                entry.setdefault("hand_index", local_idx)
                entry["session_index"] = self.next_flush_session
                entry["session_hand_index"] = local_idx
                entry["global_hand_index"] = self.global_hand_index
                entry["session_seed"] = session_seed
                self.all_summaries.append(entry)
                self.global_hand_index += 1
                self.log_manager.append(entry, self._log if self.emit_logs else None)
            self.next_flush_session += 1

    def _run_serial_jobs(self) -> None:
        for idx, session_seed in self.jobs:
            hand_cb = self._make_hand_callback(idx)
            summaries = run_demo_headless_collect(
                seed=session_seed,
                bot=self.bot,
                hands=self.hands,
                jangs=self.jangs,
                start_points=self.start_points,
                log_dir=None,
                hand_progress_cb=hand_cb,
            )
            self._record_session(idx, session_seed, summaries)
            self._finish_session(idx, len(summaries))

    def _run_parallel_jobs(self) -> None:
        manager = mp.Manager() if self.progress is not None else None
        progress_queue = manager.Queue() if manager is not None else None

        try:
            with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
                future_map = {
                    pool.submit(
                        _run_headless_batch_session,
                        idx,
                        session_seed,
                        self.bot,
                        self.hands,
                        self.jangs,
                        self.start_points,
                        progress_queue,
                    ): idx
                    for idx, session_seed in self.jobs
                }

                pending = set(future_map.keys())
                while pending:
                    if progress_queue is not None:
                        try:
                            session_idx, hand_idx = progress_queue.get(timeout=0.1)
                        except Empty:
                            pass
                        else:
                            self._update_session(session_idx, hand_idx)

                    done = [future for future in pending if future.done()]
                    for fut in done:
                        pending.remove(fut)
                        idx, session_seed, summaries = fut.result()
                        self._record_session(idx, session_seed, summaries)
                        self._finish_session(idx, len(summaries))

                if progress_queue is not None:
                    while True:
                        try:
                            session_idx, hand_idx = progress_queue.get_nowait()
                        except Empty:
                            break
                        else:
                            self._update_session(session_idx, hand_idx)
        finally:
            if manager is not None:
                manager.shutdown()


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

    runner = HeadlessBatchRunner(
        sessions=sessions,
        cores=cores,
        seed=seed,
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=log_dir,
        emit_logs=emit_logs,
    )
    return runner.run()


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
        bot=bot,
        hands=hands,
        jangs=jangs,
        start_points=start_points,
        log_dir=None,
        hand_progress_cb=_report if progress_queue is not None else None,
    )
    return session_index, session_seed, summaries
