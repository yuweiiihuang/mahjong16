from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, List

from application.session_service import ScoreState, StepEvent
from interfaces.console.ui_adapter import ConsoleUIAdapter
from interfaces.headless.log_adapter import HeadlessLogAdapter


def _make_fake_env() -> SimpleNamespace:
    rules = SimpleNamespace(base_points=None, tai_points=None)
    return SimpleNamespace(quan_feng="E", dealer_pid=0, dealer_streak=0, rules=rules)


def test_console_adapter_appends_incremental_log(tmp_path) -> None:
    adapter = ConsoleUIAdapter(
        human_pid=None,
        n_players=4,
        log_dir=str(tmp_path),
        emit_logs=False,
    )
    env = _make_fake_env()
    score_state: ScoreState = {"totals": [0, 0, 0, 0], "deltas": [0, 0, 0, 0]}
    summary: Dict[str, List[int]] = {
        "payments": [0, 0, 0, 0],
        "totals_after_hand": [0, 0, 0, 0],
    }

    adapter.on_session_start(env=env, score_state=score_state)
    adapter.on_hand_start(hand_index=1, jang_index=1, env=env, score_state=score_state)
    adapter.on_step(
        event=StepEvent(
            observation={},
            info=None,
            action={},
            acting_pid=0,
            action_type="PASS",
            discarded_tile=None,
        ),
        env=env,
        score_state=score_state,
    )
    adapter.on_hand_summary(summary)
    adapter.finalize([summary])
    adapter.on_session_end(summaries=[summary], env=env, score_state=score_state)

    files = list(tmp_path.iterdir())
    assert len(files) == 1


def test_headless_adapter_reports_progress_and_logs(tmp_path) -> None:
    progress_calls: List[int] = []

    def _progress_cb(hand_idx: int) -> None:
        progress_calls.append(hand_idx)

    adapter = HeadlessLogAdapter(
        n_players=4,
        log_dir=str(tmp_path),
        emit_logs=False,
        hand_progress_cb=_progress_cb,
    )

    summary = {"payments": [0, 0, 0, 0], "totals_after_hand": [0, 0, 0, 0]}

    adapter.on_session_start(total_hands=2)
    adapter.on_hand_complete(1)
    adapter.on_hand_summary(summary)
    adapter.finalize([summary])
    adapter.on_session_end()

    assert progress_calls == [1]
    files = list(tmp_path.iterdir())
    assert len(files) == 1
