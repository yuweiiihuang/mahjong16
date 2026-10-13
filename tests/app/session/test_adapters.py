import csv

import pytest

from app.session.adapters import ConsoleUIAdapter, HeadlessLogAdapter


@pytest.mark.parametrize("adapter_type", [ConsoleUIAdapter, HeadlessLogAdapter])
def test_adapter_appends_each_summary_before_finalize(adapter_type, tmp_path):
    options = {"human_pid": None} if adapter_type is ConsoleUIAdapter else {}
    adapter = adapter_type(n_players=4, log_dir=str(tmp_path), emit_logs=False, **options)
    summaries = [
        {"hand_index": 1, "payments": [30, -10, -10, -10],
         "totals_after_hand": [1030, 990, 990, 990]},
        {"hand_index": 2, "payments": [-20, 20, 0, 0],
         "totals_after_hand": [1010, 1010, 990, 990]},
    ]
    expected = [("1", "30", "1030"), ("2", "-20", "1010")]
    try:
        for index, summary in enumerate(summaries, 1):
            adapter.on_hand_summary(summary)
            files = list(tmp_path.iterdir())
            assert len(files) == 1
            with files[0].open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            assert [(r["hand_index"], r["delta_p0"], r["total_p0"]) for r in rows] == (
                expected[:index]
            )
    finally:
        adapter.finalize(summaries)
    with files[0].open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == rows
    assert list(tmp_path.iterdir()) == files


def test_headless_adapter_reports_each_completed_hand():
    progress_calls = []
    adapter = HeadlessLogAdapter(
        n_players=4, emit_logs=False, hand_progress_cb=progress_calls.append,
    )
    adapter.on_session_start(total_hands=2)
    adapter.on_hand_complete(1)
    adapter.on_hand_complete(2)
    adapter.on_session_end()
    assert progress_calls == [1, 2]
