from __future__ import annotations

from typing import Any, Dict, List, Optional

from application.session_service import (
    HandSummaryPort,
    ScoreState,
    SessionService,
    StepEvent,
    TableViewPort,
)
from app.table import TableManager
from app.strategies import build_strategies
from domain import Mahjong16Env, Ruleset
from domain.scoring.tables import load_scoring_assets


class RecordingTableView(TableViewPort):
    def __init__(self) -> None:
        self.events: List[tuple] = []

    def on_session_start(self, *, env: Mahjong16Env, score_state: ScoreState) -> None:
        self.events.append(("session_start", list(score_state.get("totals", []))))

    def on_hand_start(
        self,
        *,
        hand_index: int,
        jang_index: int,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.events.append(("hand_start", hand_index, jang_index))

    def on_step(
        self,
        *,
        event: StepEvent,
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.events.append(("step", event.action_type))

    def on_hand_scored(
        self,
        *,
        hand_index: int,
        breakdown: Dict[int, List[Dict[str, Any]]],
        payments: List[int],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.events.append(("hand_scored", hand_index, list(payments)))

    def on_session_end(
        self,
        *,
        summaries: List[Dict[str, Any]],
        env: Mahjong16Env,
        score_state: ScoreState,
    ) -> None:
        self.events.append(("session_end", len(summaries)))


class RecordingHandSummary(HandSummaryPort):
    def __init__(self) -> None:
        self.summaries: List[Dict[str, Any]] = []
        self.finalized: bool = False
        self.final_payload: Optional[List[Dict[str, Any]]] = None

    def on_hand_summary(self, summary: Dict[str, Any]) -> None:
        self.summaries.append(summary)

    def finalize(self, summaries: List[Dict[str, Any]]) -> None:
        self.finalized = True
        self.final_payload = list(summaries)


def test_session_service_emits_events_and_scores() -> None:
    rules = Ruleset(
        scoring_profile="taiwan_base",
        rule_profile="common",
    )
    env = Mahjong16Env(rules, seed=42)
    table_manager = TableManager(rules, seed=42)
    scoring_table = load_scoring_assets(rules.scoring_profile, rules.scoring_overrides_path)
    strategies = build_strategies(env.rules.n_players, human_pid=None, bot="auto")

    view = RecordingTableView()
    summary_port = RecordingHandSummary()

    service = SessionService(
        env=env,
        table_manager=table_manager,
        strategies=strategies,
        scoring_assets=scoring_table,
        hands=1,
        start_points=1000,
        table_view_port=view,
        hand_summary_port=summary_port,
    )

    results = service.run()

    assert len(results) == 1
    assert summary_port.summaries == results
    assert summary_port.finalized
    assert summary_port.final_payload == results

    names = [entry[0] for entry in view.events]
    assert names[0] == "session_start"
    assert "hand_start" in names
    assert "hand_scored" in names
    assert names[-1] == "session_end"
    assert names.index("hand_start") < names.index("step")
    assert names.index("hand_scored") < names.index("session_end")

    summary = results[0]
    payments = summary["payments"]
    totals = summary["totals_after_hand"]
    assert isinstance(payments, list) and len(payments) == env.rules.n_players
    assert isinstance(totals, list) and len(totals) == env.rules.n_players
    assert sum(payments) == 0
    assert totals == [1000 + delta for delta in payments]
