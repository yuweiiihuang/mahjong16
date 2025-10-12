from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence

from domain import Mahjong16Env
from domain.scoring.engine import compute_payments, score_with_breakdown
from domain.scoring.tables import ScoringTable
from domain.scoring.types import ScoringContext
from domain.tiles import tile_sort_key

from app.table import TableManager
from app.strategies import Strategy


ScoreState = Dict[str, List[int]]


@dataclass
class StepEvent:
    """Encapsulate information about a processed environment step."""

    observation: Dict[str, Any]
    info: Optional[Dict[str, Any]]
    action: Dict[str, Any]
    acting_pid: Optional[int]
    action_type: str
    discarded_tile: Optional[int]


class TableViewPort(Protocol):
    """Interface for rendering turn-by-turn table updates."""

    def on_session_start(self, *, env: Mahjong16Env, score_state: ScoreState) -> None:
        """Notify that a session is beginning."""

    def on_hand_start(
        self,
        *,
        hand_index: int,
        jang_index: int,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        """Notify that a new hand has started."""

    def on_step(
        self,
        *,
        event: StepEvent,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        """Provide the result of an environment step for rendering."""

    def on_hand_scored(
        self,
        *,
        hand_index: int,
        breakdown: Dict[int, List[Dict[str, Any]]],
        payments: List[int],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        """Deliver scoring results for a completed hand."""

    def on_session_end(
        self,
        *,
        summaries: List[Dict[str, Any]],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        """Notify that the session has completed."""


class HandSummaryPort(Protocol):
    """Interface for persisting or presenting per-hand summaries."""

    def on_hand_summary(self, summary: Dict[str, Any]) -> None:
        """Handle a newly generated hand summary."""

    def finalize(self, summaries: List[Dict[str, Any]]) -> None:
        """Finalize once the session concludes."""


class ProgressPort(Protocol):
    """Interface for reporting hand-level progress."""

    def on_session_start(self, total_hands: Optional[int]) -> None:
        """Prepare any progress indicators for a new session."""

    def on_hand_complete(self, hand_index: int) -> None:
        """Update the progress indicator after a hand completes."""

    def on_session_end(self) -> None:
        """Tear down the progress indicator when the session ends."""


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

