"""Durable-prefix, lifecycle, privacy and concurrency contracts for real web tables."""
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import threading

import pytest

from app.hand_store import HandStore, RecordingError, stored_hand, stored_hands
from app.web import WebHandler, WebTable
from app.web_rooms import RoomRegistry, WebRoom
from app import hand_store, replay
from domain.gameplay.recording import private_state, replay_hand
from domain.table import deal
from domain.tiles import is_flower


@pytest.fixture
def store(tmp_path):
    database = HandStore(tmp_path / 'hands.sqlite3')
    yield database
    database.close()


def _room(store, seed=7):
    room = WebRoom('1234ABCD', 'private-cookie-host', WebTable(
        seed, human_pids={0, 1, 2, 3}, record_store=store, defer_recording=True))
    with room.changed:
        room.join('private-cookie-guest', '朋友')
        room.start('private-cookie-host')
        room.ready_at = 0
    return room


def _document(store, table):
    return stored_hand(store.path, table.env.recorder.records[-1]['hand_id'])


def test_lobby_handoff_retry_and_private_export(store):
    registry = RoomRegistry()
    factory = lambda **kwargs: WebTable(
        7, **kwargs, record_store=store, defer_recording=True)
    room = registry.create('private-cookie-host', factory, '房主')
    registry.join('private-cookie-guest', room.code, '朋友')
    assert stored_hands(store.path) == []
    with room.changed:
        room.start('private-cookie-host')
        room.ready_at = 0
        assert len(stored_hands(store.path)) == 1
        before = room.snapshot('private-cookie-host')
        action = next(a for a in before['legal_actions'] if a['type'] == 'DISCARD')
        room.act('private-cookie-host', room.version, 'once', action)
        saved = _document(store, room.table)
        room.act('private-cookie-host', before['version'], 'once', action)
        assert _document(store, room.table) == saved
    registry.leave('private-cookie-guest')
    registry.join('private-cookie-new', room.code, '接替朋友')
    saved = _document(store, room.table)
    assert [event['human'] for event in saved['metadata']['seat_events']] == [False, True]
    assert saved['metadata']['players'][1]['name'] == '朋友'
    assert saved['metadata']['seat_events'][-1]['name'] == '接替朋友'
    assert saved['metadata']['players'][1]['player_id'] != (
        saved['metadata']['seat_events'][-1]['player_id'])
    assert saved['metadata']['decisions'][0]['source'] == 'human'
    assert any(step['source'] == 'auto_pass' for step in saved['metadata']['decisions'])
    assert 'private-cookie' not in json.dumps(saved)
    assert private_state(replay_hand(saved)) == private_state(room.table.env)
    snapshot = room.snapshot('private-cookie-host')
    assert all(key not in snapshot for key in ('metadata', 'setup', 'initial_state', 'steps'))
    assert saved['metadata']['table_id'] not in json.dumps(snapshot)


def test_completed_settlement_backup_and_restart_preserve_records(store, tmp_path):
    room = _room(store)
    with room.changed:
        for pid in (2, 3):
            room.join(f'private-cookie-{pid}')
        for sequence in range(1000):
            if room.table.env.done:
                break
            room.ready_at = 0
            pid = room.table.actor()
            action = room.table.bot.choose(room.table.env._obs(pid))
            room.act(room.seats[pid], room.version, str(sequence), action)
        assert room.table.env.done
        completed = _document(store, room.table)
        assert completed['storage_status'] == 'completed'
        assert completed['settlement']['payments'] == room.table.settlement['payments']
        assert completed['metadata']['totals_after'] == room.table.totals
        assert private_state(replay_hand(completed)) == private_state(room.table.env)
        room.table.settle()
        assert _document(store, room.table) == completed
        room.start('private-cookie-host', next_hand=True)
        pending = _document(store, room.table)
        assert pending['metadata']['hand_index'] == 2
        assert pending['metadata']['totals_before'] == completed['metadata']['totals_after']
    backup = tmp_path / 'backup.sqlite3'
    store.backup(backup)
    assert stored_hand(backup, completed['hand_id']) == completed
    with pytest.raises(FileExistsError):
        store.backup(backup)
    # Release ownership without deleting the file; the new process marks unfinished hands.
    store.close()
    reopened = HandStore(store.path)
    try:
        restored = stored_hand(store.path, pending['hand_id'])
        assert restored['storage_status'] == 'interrupted'
        assert restored['interruption_reason'] == 'server_restart'
        assert restored['status'] == 'incomplete' and restored['settlement'] is None
        replay_hand(restored)
        assert stored_hand(store.path, completed['hand_id']) == completed
    finally:
        reopened.close()


def test_write_failure_stops_only_affected_table_and_keeps_durable_prefix(store, monkeypatch):
    bad = _room(store)
    good = _room(store, seed=12)
    prefix = _document(store, bad.table)
    save = store.save

    def fail_one(document, metadata):
        if metadata['table_id'] == bad.table.table_id:
            raise sqlite3.OperationalError('disk full / private filesystem detail')
        save(document, metadata)

    monkeypatch.setattr(store, 'save', fail_one)
    with bad.changed:
        action = next(a for a in bad.table.env.legal_actions(0) if a['type'] == 'DISCARD')
        with pytest.raises(RecordingError, match='已暫停') as failure:
            bad.act('private-cookie-host', bad.version, 'failed', action)
        assert 'private filesystem' not in str(failure.value)
        assert bad.table.recording_error and not bad.requests
        assert _document(store, bad.table) == prefix
        frozen = private_state(bad.table.env)
        with pytest.raises(RecordingError):
            bad.act('private-cookie-host', bad.version, 'failed', action)
        bad.tick(10**9)
        assert private_state(bad.table.env) == frozen
    with good.changed:
        action = next(a for a in good.table.env.legal_actions(0) if a['type'] == 'DISCARD')
        good.act('private-cookie-host', good.version, 'good', action)
        assert _document(store, good.table)['steps']
    assert private_state(replay_hand(prefix)) != frozen


def test_terminal_write_failure_keeps_an_unfinished_prefix(store, monkeypatch):
    room = _room(store)
    save = store.save

    def fail_completed(document, metadata):
        if document['status'] == 'completed' and 'totals_after' in metadata:
            raise sqlite3.OperationalError('settlement write failed')
        save(document, metadata)

    monkeypatch.setattr(store, 'save', fail_completed)
    with room.changed:
        for pid in (2, 3):
            room.join(f'private-cookie-{pid}')
        with pytest.raises(RecordingError):
            for sequence in range(1000):
                room.ready_at = 0
                pid = room.table.actor()
                action = room.table.bot.choose(room.table.env._obs(pid))
                room.act(room.seats[pid], room.version, str(sequence), action)
    prefix = _document(store, room.table)
    assert prefix['storage_status'] == 'active'
    assert prefix['status'] == 'incomplete' and prefix['settlement'] is None
    assert not replay_hand(prefix).done
    assert room.table.recording_error


def test_initial_flower_win_commits_once_with_table_totals(store, monkeypatch):
    full_wall = deal.full_wall
    monkeypatch.setattr(deal, 'full_wall', lambda include, rng: sorted(
        full_wall(include, rng), key=is_flower))
    saved = []
    save = store.save

    def capture(document, metadata):
        saved.append((document['status'], dict(metadata)))
        save(document, metadata)

    monkeypatch.setattr(store, 'save', capture)
    table = WebTable(7, human_pids={0, 1, 2, 3}, record_store=store)
    assert table.env.done and table.env.flower_win_type == 'ba_xian'
    assert len(saved) == 1 and saved[0][0] == 'completed'
    assert saved[0][1]['totals_after'] == table.totals
    record = _document(store, table)
    assert record['steps'] == []
    assert record['metadata']['settlement'] == table.settlement
    assert private_state(replay_hand(record)) == private_state(table.env)


def test_failed_handoff_does_not_reserve_a_ghost_seat(store, monkeypatch):
    registry = RoomRegistry()
    room = registry.create('host', lambda **kwargs: WebTable(
        7, **kwargs, record_store=store, defer_recording=True))
    with room.changed:
        room.start('host')
    prefix = _document(store, room.table)

    def failed_save(*_):
        raise sqlite3.OperationalError('handoff write failed')

    monkeypatch.setattr(store, 'save', failed_save)
    with pytest.raises(RecordingError):
        registry.join('new-player', room.code, '朋友')
    assert 'new-player' not in room.seats
    assert 'new-player' not in room.names
    assert 'new-player' not in registry.memberships
    assert _document(store, room.table) == prefix
    assert registry.create('new-player', lambda **kwargs: WebTable(
        7, **kwargs, record_store=store, defer_recording=True))


@pytest.mark.parametrize('command', ['record', 'export', 'backup'])
def test_private_cli_outputs_reject_public_root(store, tmp_path, monkeypatch, command):
    table = WebTable(7, human_pids={0, 1, 2, 3}, record_store=store)
    public = tmp_path / 'ui/web'
    public.mkdir(parents=True)
    # Isolate the public directory; never write private test data to the real server root.
    monkeypatch.setattr(hand_store, '__file__', str(tmp_path / 'app/hand_store.py'))
    target = public / 'private-record'
    args = ['replay', command, str(target)]
    if command != 'record':
        args += ['--db', str(store.path)]
    if command == 'export':
        args += ['--hand-id', _document(store, table)['hand_id']]
    monkeypatch.setattr('sys.argv', args)
    with pytest.raises(SystemExit) as failure:
        replay.main()
    assert failure.value.code == 1
    assert not target.exists()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX permissions; Windows uses host ACLs')
@pytest.mark.parametrize('command', ['record', 'export'])
def test_private_json_created_with_owner_only_permissions(store, tmp_path, monkeypatch, command):
    table = WebTable(7, human_pids={0, 1, 2, 3}, record_store=store)
    target = tmp_path / f'{command}.json'
    args = ['replay', command, str(target)]
    if command == 'export':
        args += ['--db', str(store.path), '--hand-id', _document(store, table)['hand_id']]
    monkeypatch.setattr('sys.argv', args)
    previous = os.umask(0o022)
    try:
        replay.main()
    finally:
        os.umask(previous)
    assert target.stat().st_mode & 0o777 == 0o600


def test_one_database_owner_and_concurrent_rooms(store):
    with pytest.raises(OSError):
        HandStore(store.path)
    rooms = [_room(store, seed=seed) for seed in (7, 12)]
    errors = []

    def play(room):
        try:
            with room.changed:
                action = next(a for a in room.table.env.legal_actions(0)
                              if a['type'] == 'DISCARD')
                room.act('private-cookie-host', room.version, 'one', action)
        except Exception as error:
            errors.append(error)

    workers = [threading.Thread(target=play, args=(room,)) for room in rooms]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)
    assert not errors and all(not worker.is_alive() for worker in workers)
    assert len(stored_hands(store.path)) == 2
    for room in rooms:
        assert private_state(replay_hand(_document(store, room.table))) == (
            private_state(room.table.env))


def test_practice_replaced_hand_retains_interrupted_prefix(store):
    table = WebTable(7, record_store=store)
    first = _document(store, table)
    table.new_table()
    interrupted = stored_hand(store.path, first['hand_id'])
    assert interrupted['storage_status'] == 'interrupted'
    assert interrupted['interruption_reason'] == 'new_table'
    assert private_state(replay_hand(interrupted)) == private_state(replay_hand(first))
    assert len(stored_hands(store.path)) == 2


def test_database_cannot_be_created_in_static_web_root():
    root = Path(__file__).resolve().parents[2] / 'ui/web'
    with pytest.raises(ValueError, match='公開目錄'):
        HandStore(root / 'private.sqlite3')
    assert not (root / 'private.sqlite3').exists()


def test_http_saved_action_retry_and_storage_failure_response(store, monkeypatch):
    class Handler(WebHandler):
        sessions = {}
        session_seen = {}
        rooms = RoomRegistry()
        record_store = store

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, body=None, cookie=''):
        connection = http.client.HTTPConnection(*server.server_address, timeout=3)
        connection.request('POST' if body is not None else 'GET', path,
                           json.dumps(body) if body is not None else None,
                           {'Content-Type': 'application/json', 'Cookie': cookie})
        response = connection.getresponse()
        result = response.status, json.loads(response.read()), (
            response.getheader('Set-Cookie', cookie).split(';')[0])
        connection.close()
        return result

    try:
        status, state, host = request('/api/rooms', {'name': '房主'})
        assert status == 200 and stored_hands(store.path) == []
        for index in range(3):
            assert request('/api/room/join', {'code': state['room']['code'],
                                            'name': f'朋友{index}'})[0] == 200
        assert request('/api/room/start', {}, host)[0] == 200
        room = Handler.rooms.get(host.split('=')[1])
        with room.changed:
            room.ready_at = 0
        state = request('/api/room/state', cookie=host)[1]
        action = next(a for a in state['legal_actions'] if a['type'] == 'DISCARD')
        body = {'action': action, 'request_id': 'one', 'version': state['version']}
        assert request('/api/room/action', body, host)[0] == 200
        saved = _document(store, room.table)
        assert request('/api/room/action', body, host)[0] == 200
        assert _document(store, room.table) == saved
        # A fresh practice table also uses the same persistent path and error contract.
        status, practice, player = request('/api/state')
        assert status == 200
        table = Handler.sessions[player.split('=')[1]]
        prefix = _document(store, table)

        def failed_save(*_):
            raise sqlite3.OperationalError('simulated disk failure')

        monkeypatch.setattr(store, 'save', failed_save)
        action = next(a for a in practice['legal_actions'] if a['type'] == 'DISCARD')
        status, failure, _ = request('/api/action', action, player)
        assert status == 503 and '已暫停' in failure['error']
        assert request('/api/state', cookie=player)[0] == 503
        assert _document(store, table) == prefix
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
