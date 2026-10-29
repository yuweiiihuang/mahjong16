"""Real HTTP authorization, anonymous reconnect, history and shared-table recovery."""
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import http.client
import json
import threading
from unittest.mock import patch

import pytest

from app.hand_store import HandStore
from app.web import WebHandler, WebTable
from app.web_rooms import RoomRegistry
from domain.gameplay.recording import private_state


@contextmanager
def server(path):
    store = HandStore(path)

    class SeededTable(WebTable):
        def __init__(self, **kwargs):
            super().__init__(seed=7, **kwargs)

    class Handler(WebHandler):
        sessions = {}
        session_seen = {}
        rooms = RoomRegistry()
        record_store = store

        def log_message(self, *args):
            pass

    with patch('app.web.WebTable', SeededTable):
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield httpd.server_address, Handler, store
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()
            store.close()


def call(address, path, cookie='', body=None, headers=None):
    connection = http.client.HTTPConnection(*address, timeout=10)
    try:
        connection.request('POST' if body is not None else 'GET', path,
                           json.dumps(body) if body is not None else None,
                           {'Content-Type': 'application/json', 'Cookie': cookie,
                            **(headers or {})})
        response = connection.getresponse()
        return response.status, json.loads(response.read()), response.getheader('Set-Cookie')
    finally:
        connection.close()


def test_history_replay_and_reconnect_do_not_expose_other_players(tmp_path):
    with server(tmp_path / 'hands.sqlite3') as (address, handler, store):
        status, state, cookie = call(address, '/api/state')
        cookie = cookie.split(';')[0]
        assert status == 200
        sid = cookie.partition('=')[2]
        table = handler.sessions[sid]
        while not table.env.done:
            table.act(table.bot.choose(table.env._obs(0)))
        final = table.snapshot()
        status, result, _ = call(address, '/api/history', cookie)
        assert status == 200 and len(result['hands']) == 1
        item = result['hands'][0]
        assert item['payment'] == final['totals'][0] - 1000
        assert item['resumable'] and item['replayable']
        assert not {'players', 'setup', 'steps', 'recovery'} & item.keys()
        status, replay, _ = call(address, '/api/replay?hand_id=' + item['id'], cookie)
        assert status == 200
        assert replay['frames'][-1]['state']['totals'] == final['totals']
        for frame in replay['frames'][:-1]:
            assert 'final_hands' not in frame['state']
            assert all('hand' not in player for player in frame['state']['players'])
            assert not frame['state']['legal_actions']
        original = private_state(table.env)
        replay_ids = [frame['seq'] for frame in replay['frames']]
        for viewer in range(4):
            status, other, _ = call(address, '/api/replay?hand_id=' + item['id'] +
                                    f'&view={viewer}', cookie)
            assert status == 200
            frames = other['frames']
            assert [frame['seq'] for frame in frames] == replay_ids
            assert frames[0]['state']['hand'] == table.env.recorder.records[-1][
                'initial_state']['players'][viewer]['hand']
            assert frames[-1]['state']['player'] == 0
            assert frames[-1]['state']['totals'] == final['totals'][viewer:] + final['totals'][:viewer]
            assert all(not frame['state']['legal_actions'] for frame in frames)
            assert all('wall' not in frame['state'] for frame in frames)
            assert all(frame['event'] is None or frame['event']['type'] != 'PASS'
                       for frame in frames)
        assert private_state(table.env) == original, 'replay never changes the live engine'
        for view in ('-1', '4', 'abc', '1.5'):
            assert call(address, '/api/replay?hand_id=' + item['id'] + '&view=' + view,
                        cookie)[0] == 400
        status, _, stranger = call(address, '/api/state')
        stranger = stranger.split(';')[0]
        assert call(address, '/api/replay?hand_id=' + item['id'], stranger)[0] == 400
        assert call(address, '/api/resume', stranger, {'hand_id': item['id']})[0] == 400
        handler.sessions.clear()  # Lose all in-memory sessions, retain only durable identity.
        handler.session_seen.clear()
        status, _, replacement = call(address, '/api/history', cookie)
        assert status == 200 and replacement.split(';')[0] == cookie
        assert 'Max-Age=31536000' in replacement, 'anonymous identity survives browser closure'
        status, resumed, _ = call(address, '/api/resume', cookie, {'hand_id': item['id']})
        assert status == 200 and resumed['totals'] == final['totals']
        assert resumed['done'] and resumed['round'] == 1
        status, next_hand, _ = call(address, '/api/next', cookie, {})
        assert status == 200 and next_hand['round'] == 2
        assert call(address, '/api/resume', cookie, {'hand_id': item['id']})[0] == 400


def test_shared_recovery_reserves_seats_and_remembers_accepted_requests(tmp_path):
    with server(tmp_path / 'hands.sqlite3') as (address, handler, store):
        _, _, host_cookie = call(address, '/api/state')
        host_cookie = host_cookie.split(';')[0]
        _, _, guest_cookie = call(address, '/api/state')
        guest_cookie = guest_cookie.split(';')[0]
        _, state, _ = call(address, '/api/rooms', host_cookie, {'name': '房主'})
        code = state['room']['code']
        assert call(address, '/api/room/join', guest_cookie, {'code': code, 'name': '朋友'})[0] == 200
        assert call(address, '/api/room/start', host_cookie, {})[0] == 200
        room = handler.rooms.rooms[code]
        with room.changed:
            room.ready_at = 0
            action = next(a for a in room.table.env.legal_actions(0) if a['type'] == 'DISCARD')
            room.act(room.seats[0], room.version, 'accepted-before-crash', action)
        saved = private_state(room.table.env)
        _, result, _ = call(address, '/api/history', host_cookie)
        item = result['hands'][0]
        handler.rooms = RoomRegistry()
        handler.sessions.clear()
        status, resumed, _ = call(address, '/api/resume', guest_cookie, {'hand_id': item['id']})
        assert status == 200 and resumed['room']['members'][0]['name'] == '朋友'
        assert not resumed['room']['host']
        recovered = handler.rooms.rooms[code]
        assert private_state(recovered.table.env) == saved
        status, host_state, _ = call(address, '/api/resume', host_cookie, {'hand_id': item['id']})
        assert status == 200 and host_state['room']['host']
        assert host_state['room']['members'][1]['name'] == '朋友'
        body = {'request_id': 'accepted-before-crash', 'version': -1, 'action': action}
        assert call(address, '/api/room/action', host_cookie, body)[0] == 200
        assert private_state(recovered.table.env) == saved
        assert len(handler.rooms.rooms) == 1
        with recovered.changed:
            while not recovered.table.env.done:
                actor = recovered.table.actor()
                recovered.apply(recovered.table.bot.choose(recovered.table.env._obs(actor)),
                                pid=actor, source='bot')
            recovered.start(recovered.seats[0], next_hand=True)
        next_state = private_state(recovered.table.env)
        _, records, _ = call(address, '/api/history', host_cookie)
        next_id = records['hands'][0]['id']
        handler.rooms = RoomRegistry()
        assert call(address, '/api/resume', host_cookie, {'hand_id': next_id})[0] == 200
        assert call(address, '/api/room/action', host_cookie, body)[0] == 200
        assert private_state(handler.rooms.rooms[code].table.env) == next_state


def test_failed_save_can_resume_only_the_last_committed_prefix(tmp_path, monkeypatch):
    import sqlite3

    with server(tmp_path / 'hands.sqlite3') as (address, handler, store):
        _, state, cookie = call(address, '/api/state')
        cookie = cookie.split(';')[0]
        sid = cookie.partition('=')[2]
        table = handler.sessions[sid]
        saved = private_state(table.env)
        _, result, _ = call(address, '/api/history', cookie)
        hand_id = result['hands'][0]['id']
        action = next(action for action in state['legal_actions'] if action['type'] == 'DISCARD')
        with monkeypatch.context() as patch:
            def fail(*args):
                raise sqlite3.OperationalError('disk full')
            patch.setattr(store, 'save', fail)
            assert call(address, '/api/action', cookie, action)[0] == 503
            assert call(address, '/api/state', cookie)[0] == 503
        status, _, _ = call(address, '/api/resume', cookie, {'hand_id': hand_id})
        assert status == 200
        assert private_state(handler.sessions[sid].env) == saved
        assert call(address, '/api/action', cookie, action)[0] == 200


@pytest.mark.parametrize('seed', [0, 19, 42])
def test_replay_events_follow_adjudication_and_hide_private_reactions(tmp_path, seed):
    from app.web_records import replay_frames

    store = HandStore(tmp_path / 'replay.sqlite3')
    try:
        table = WebTable(seed, record_store=store, player_id='participant')
        incomplete = store.player_records('participant')[0]
        for viewer in range(4):
            with pytest.raises(ValueError, match='未完成'):
                replay_frames(incomplete, 'participant', viewer)
        while not table.env.done:
            table.act(table.bot.choose(table.env._obs(0)))
        document = store.player_records('participant')[0]
        frames = replay_frames(document, 'participant')
        expected = []
        for step in document['steps']:
            resolved = step['info'].get('resolved_claim')
            if step['done']:
                expected.append('HU' if table.env.winner is not None else 'DRAW_GAME')
            elif resolved:
                expected.append(resolved['type'])
            elif step['phase'] == 'TURN' and step['action']['type'] != 'PASS':
                expected.append(step['action']['type'])
        assert [frame['event']['type'] for frame in frames[1:]] == expected
        assert len(frames) < len(document['steps']) + 1
        assert frames[-1]['state']['done']
        assert frames[-1]['seq'] == len(document['steps'])
        assert frames[-1]['state']['settlement']['payments'] == table.settlement['payments']
        for viewer in range(4):
            for frame in replay_frames(document, 'participant', viewer)[:-1]:
                for pid, melds in enumerate(frame['state']['melds_all']):
                    if pid != 0:
                        assert all(meld['tiles'] == [None]*4 for meld in melds
                                   if meld['type'] == 'ANGANG')
                assert frame['state']['reaction_choice'] is None
        with pytest.raises(ValueError):
            replay_frames(document, 'stranger', 1)
    finally:
        store.close()


def test_multiplayer_resume_reloads_prefix_committed_after_initial_read(tmp_path, monkeypatch):
    import sqlite3
    from app.hand_store import RecordingError

    with server(tmp_path / 'hands.sqlite3') as (address, handler, store):
        _, _, cookie = call(address, '/api/state')
        cookie = cookie.split(';')[0]
        _, state, _ = call(address, '/api/rooms', cookie, {'name': '房主'})
        assert call(address, '/api/room/start', cookie, {})[0] == 200
        room = handler.rooms.rooms[state['room']['code']]
        player_id = room.record_ids[room.seats[0]]
        hand_id = store.player_records(player_id)[0]['hand_id']
        read = store.player_records
        committed = []
        original = next(action for action in room.table.env.legal_actions(0)
                        if action['type'] == 'DISCARD')

        def read_then_fail(player, *, hand_id=None):
            records = read(player, hand_id=hand_id)
            if hand_id and not committed:
                # Other room work commits once, then freezes after the resume read.
                with room.changed:
                    room.table.apply(original, pid=0)
                    committed.append(private_state(room.table.env))
                    with monkeypatch.context() as failure:
                        def fail(*args, **kwargs):
                            raise sqlite3.OperationalError('disk full')
                        failure.setattr(store, 'save', fail)
                        pid = room.table.actor()
                        action = room.table.bot.choose(room.table.env._obs(pid))
                        with pytest.raises(RecordingError):
                            room.table.apply(action, pid=pid)
            return records

        monkeypatch.setattr(store, 'player_records', read_then_fail)
        status, _, _ = call(address, '/api/resume', cookie, {'hand_id': hand_id})
        assert status == 200
        restored = handler.rooms.rooms[room.code]
        assert private_state(restored.table.env) == committed[0]
        assert read(player_id, hand_id=hand_id)[0]['steps'][0]['action'] == original
        with restored.changed:
            pid = restored.table.actor()
            restored.table.apply(restored.table.bot.choose(restored.table.env._obs(pid)), pid=pid)
        assert read(player_id, hand_id=hand_id)[0]['steps'][0]['action'] == original


def test_http_fixture_deals_are_repeatable(tmp_path):
    initial = []
    for index in range(2):
        with server(tmp_path / f'fixture-{index}.sqlite3') as (address, handler, _):
            _, _, cookie = call(address, '/api/state')
            sid = cookie.split(';')[0].partition('=')[2]
            initial.append(private_state(handler.sessions[sid].env))
    assert initial[0] == initial[1]
