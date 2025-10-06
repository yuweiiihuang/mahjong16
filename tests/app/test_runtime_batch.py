from app.runtime import run_demo_headless_batch


def test_headless_batch_creates_single_log(tmp_path):
    log_dir = tmp_path / "batch_logs"
    summaries = run_demo_headless_batch(
        sessions=2,
        cores=1,
        seed=123,
        bot="auto",
        hands=1,
        start_points=500,
        log_dir=str(log_dir),
        emit_logs=False,
    )

    assert len(summaries) == 2
    session_indices = {entry["session_index"] for entry in summaries}
    assert session_indices == {0, 1}

    global_indices = [entry["global_hand_index"] for entry in summaries]
    assert sorted(global_indices) == [1, 2]
    assert all(entry["session_seed"] is not None for entry in summaries)

    files = list(log_dir.iterdir())
    assert len(files) == 1

    with files[0].open() as handle:
        header = next(handle)
        assert "session_index" in header
        assert "global_hand_index" in header
