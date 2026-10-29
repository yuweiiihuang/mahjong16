"""Restore committed engine prefixes, including RNG and exactly-once settlement."""
from copy import deepcopy

import pytest

from app.hand_store import HandStore, stored_hand
from app.web import WebTable
from domain.gameplay.recording import private_state, replay_hand


def document(store, table):
    return stored_hand(store.path, table.env.recorder.records[-1]['hand_id'])


def play_step(table):
    pid = table.actor()
    table.apply(table.bot.choose(table.env._obs(pid)), pid=pid, source='bot')
    if table.env.done:
        table.settle()


def test_restart_restores_reaction_and_future_hands(tmp_path):
    path = tmp_path / 'hands.sqlite3'
    with_store = HandStore(path)
    table = WebTable(7, human_pids={0, 1, 2, 3}, record_store=with_store)
    # Stop immediately after a discard opens a simultaneous reaction window.
    while table.env.phase != 'REACTION':
        play_step(table)
    original = document(with_store, table)
    before = private_state(table.env)
    with_store.close()
    store = HandStore(path)
    try:
        restored = WebTable.restore(document(store, table), store)
        assert private_state(restored.env) == before
        assert restored.table_id == table.table_id
        while not restored.env.done:
            play_step(restored)
        replay_hand(document(store, restored))
        # Continue the uninterrupted branch independently and compare outcome and next deal.
        table.env.recorder = None
        table.recording_enabled = False
        while not table.env.done:
            play_step(table)
        assert restored.totals == table.totals
        totals = list(restored.totals)
        finished = document(store, restored)
        resumed_finished = WebTable.restore(finished, store)
        resumed_finished.settle()
        assert resumed_finished.totals == totals
        for candidate in (table, restored, resumed_finished):
            candidate.human_pids = {0, 1, 2, 3}
            candidate.start_hand()
        assert private_state(table.env) == private_state(restored.env)
        assert private_state(restored.env) == private_state(resumed_finished.env)
        assert restored.env.wall != original['setup']['wall']
        assert resumed_finished.round == 2
        replay_hand(document(store, resumed_finished))
    finally:
        store.close()


def test_restore_rejects_incompatible_or_corrupt_records(tmp_path):
    store = HandStore(tmp_path / 'hands.sqlite3')
    try:
        table = WebTable(7, record_store=store)
        original = document(store, table)
        for field in ('engine_version', 'final_hash'):
            broken = deepcopy(original)
            broken[field] = 'wrong'
            with pytest.raises(ValueError):
                WebTable.restore(broken, store)
        old = deepcopy(original)
        old['metadata'].pop('recovery')
        with pytest.raises(ValueError, match='續局資訊'):
            WebTable.restore(old, store)
    finally:
        store.close()


def test_snapshot_uses_current_hand_jang_and_replay_player_control(tmp_path):
    """Settlement must not display the next hand's jang on the table just finished."""
    from app.web_records import replay_frames

    store = HandStore(tmp_path / 'hud.sqlite3')
    try:
        table = WebTable(7, record_store=store)
        table.hand_manager_state['jang_count'] = 2
        table.manager.state.jang_count = 3
        snapshot = table.snapshot()
        assert snapshot['jang_count'] == 2
        while not table.env.done:
            table.act(table.bot.choose(table.env._obs(0)))
        recorded = document(store, table)
        player_id = table.record_players[0]['player_id']
        frames = replay_frames(recorded, player_id, viewer=1)
        assert {frame['state']['jang_count'] for frame in frames} == {2}
        assert frames[0]['state']['replay_humans'] == [False, False, False, True]
        del recorded['metadata']['recovery']
        assert replay_frames(recorded, player_id)[0]['state']['jang_count'] is None
    finally:
        store.close()
