"""Verified gateway accounts own seats; browser cookies and request bodies cannot choose them."""

import http.client
import hmac
from functools import partial
from http.server import ThreadingHTTPServer
import json
import sqlite3
import threading
import time

import pytest

from app.hand_store import HandStore, stored_hand, stored_hands
from app.web import WebHandler, WebTable
from app.web_rooms import RoomRegistry
from app.training_export import decision_samples


ISSUER = 'http://localhost:18081'
AUTHORIZATION = 'Basic c3RhZ2U6cHJpdmF0ZS1nYXRld2F5'


@pytest.fixture
def account_server(tmp_path, monkeypatch):
    store = HandStore(tmp_path / 'hands.sqlite3')
    monkeypatch.setattr('app.web.WebTable', partial(WebTable, 7))

    class Handler(WebHandler):
        protocol_version = 'HTTP/1.1'
        sessions = {}
        session_seen = {}
        rooms = RoomRegistry()
        access_authorization = AUTHORIZATION.encode()
        trusted_identity_issuer = ISSUER

        def log_message(self, *args):
            pass

    Handler.record_store = store
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address, Handler, store
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    store.close()


def call(address, path, subject='account-one', body=None, headers=None, connection=None):
    own_connection = connection is None
    connection = connection or http.client.HTTPConnection(*address, timeout=5)
    outgoing = {'Authorization': AUTHORIZATION, 'X-Qinghe-Subject': subject,
                'Content-Type': 'application/json', **(headers or {})}
    try:
        connection.request('POST' if body is not None else 'GET', path,
                           json.dumps(body) if body is not None else None, outgoing)
        response = connection.getresponse()
        payload = response.read()
        return response.status, dict(response.getheaders()), payload
    finally:
        if own_connection:
            connection.close()


@pytest.mark.parametrize('headers', [
    {'Authorization': ''}, {'Authorization': 'Basic forged'},
    {'X-Qinghe-Subject': ''}, {'X-Qinghe-Subject': 'one,two'},
])
def test_gateway_identity_fails_closed_before_allocating_tables(account_server, headers):
    address, handler, store = account_server
    status, _, _ = call(address, '/api/state', headers=headers)
    assert status == 401
    assert not handler.sessions and not stored_hands(store.path)


def test_legacy_access_cookie_cannot_authenticate_gateway_accounts(account_server):
    address, handler, store = account_server
    # Even a valid legacy signature cannot replace the gateway's per-request credential.
    expiry = str(int(time.time()) + 3600)
    signature = hmac.new(handler.access_authorization, expiry.encode(), 'sha256').hexdigest()
    cookie = f'qinghe_access_{address[1]}={expiry}.{signature}'
    status, _, _ = call(address, '/api/state',
                        headers={'Authorization': '', 'Cookie': cookie})
    assert status == 401 and not handler.sessions and not stored_hands(store.path)


def test_account_reconnects_without_cookies_and_switch_does_not_reuse_a_seat(
        account_server, monkeypatch):
    address, handler, store = account_server
    clock = [100.0]
    monkeypatch.setattr('app.web_rooms.time.monotonic', lambda: clock[0])
    status, headers, payload = call(address, '/api/rooms', body={'name': '同名'})
    assert status == 200
    assert 'Set-Cookie' not in headers
    first = json.loads(payload)
    code = first['room']['code']
    # A different device carries no game cookie but must find this account's existing seat.
    status, _, payload = call(address, '/api/state')
    assert status == 200 and json.loads(payload)['room']['code'] == code
    assert len(handler.rooms.rooms[code].seats) == 4
    assert sum(seat is not None for seat in handler.rooms.rooms[code].seats) == 1
    # Same TCP connection and old browser cookie: account B must not inherit A's room or hand.
    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        assert call(address, '/api/state', connection=connection)[0] == 200
        status, _, payload = call(address, '/api/room/state', subject='account-two',
                                  headers={'Cookie': f'qinghe_{address[1]}=account-one'},
                                  connection=connection)
        assert status == 400 and 'room' not in json.loads(payload)
        status, _, payload = call(address, '/api/room/join', subject='account-two',
                                  body={'code': code, 'name': '同名', 'player_id': 'account-one'},
                                  connection=connection)
        assert status == 200 and not json.loads(payload)['room']['host']
    finally:
        connection.close()
    status, _, payload = call(address, '/api/room/start', body={})
    assert status == 200
    clock[0] += 1
    status, _, payload = call(address, '/api/state')
    assert status == 200
    state = json.loads(payload)
    discard = next(action for action in state['legal_actions'] if action['type'] == 'DISCARD')
    assert call(address, '/api/room/action', body={
        'version': state['version'], 'request_id': 'account-discard', 'action': discard})[0] == 200
    saved = stored_hand(store.path, stored_hands(store.path)[0]['hand_id'])
    players = saved['metadata']['players']
    assert players[0]['player_id'] != players[1]['player_id']
    assert saved['metadata']['decisions'][0]['player_id'] == players[0]['player_id']
    samples = decision_samples(saved, include_incomplete=True)
    assert samples[0]['player_id'] == players[0]['player_id']
    serialized = json.dumps(saved)
    assert 'account-one' not in serialized and 'account-two' not in serialized
    assert ISSUER not in serialized and AUTHORIZATION not in serialized
    # Account A's next room retains the same private ID even after releasing its seat.
    assert call(address, '/api/room/leave', body={})[0] == 200
    assert call(address, '/api/rooms', body={'name': '新名字'})[0] == 200
    assert call(address, '/api/room/start', body={})[0] == 200
    records = [stored_hand(store.path, row['hand_id']) for row in stored_hands(store.path)]
    assert all(doc['metadata']['players'][0]['player_id'] == players[0]['player_id']
               for doc in records)


def test_practice_uses_the_same_account_id_after_new_table(account_server):
    address, handler, store = account_server
    assert call(address, '/api/state')[0] == 200
    assert call(address, '/api/start', body={})[0] == 200
    table = next(iter(handler.sessions.values()))
    while not table.env.done:
        table.act(table.bot.choose(table.env._obs(0)))
    assert call(address, '/api/new', body={})[0] == 200
    assert call(address, '/api/start', body={})[0] == 200
    documents = [stored_hand(store.path, row['hand_id']) for row in stored_hands(store.path)]
    ids = [doc['metadata']['players'][0]['player_id'] for doc in documents]
    assert len(ids) == 2 and ids[0] == ids[1]


def test_mid_hand_join_records_account_at_the_handoff_not_the_initial_seat(account_server):
    address, _, store = account_server
    status, _, payload = call(address, '/api/rooms', body={})
    assert status == 200
    code = json.loads(payload)['room']['code']
    assert call(address, '/api/room/start', body={})[0] == 200
    assert call(address, '/api/room/join', subject='account-two',
                body={'code': code, 'name': '接替朋友'})[0] == 200
    saved = stored_hand(store.path, stored_hands(store.path)[0]['hand_id'])
    assert saved['metadata']['players'][1]['player_id'] is None
    event = saved['metadata']['seat_events'][0]
    assert event['pid'] == 1 and event['human'] and event['name'] == '接替朋友'
    joined_player = event['player_id']
    assert joined_player and joined_player != saved['metadata']['players'][0]['player_id']
    assert call(address, '/api/room/leave', subject='account-two', body={})[0] == 200
    assert call(address, '/api/rooms', subject='account-two', body={})[0] == 200
    assert call(address, '/api/room/start', subject='account-two', body={})[0] == 200
    documents = [stored_hand(store.path, row['hand_id']) for row in stored_hands(store.path)]
    assert any(doc['metadata']['players'][0]['player_id'] == joined_player for doc in documents)


def test_duplicate_subject_headers_are_rejected_before_dispatch(account_server):
    address, handler, _ = account_server
    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.putrequest('GET', '/api/state')
        connection.putheader('Authorization', AUTHORIZATION)
        connection.putheader('X-Qinghe-Subject', 'account-one')
        connection.putheader('X-Qinghe-Subject', 'account-two')
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 401
        response.read()
    finally:
        connection.close()
    assert not handler.sessions


def test_account_mapping_survives_restart_without_rewriting_old_records(tmp_path):
    path = tmp_path / 'hands.sqlite3'
    # A version-1 database must upgrade without deleting a historical hand.
    store = HandStore(path)
    table = WebTable(7, record_store=store)
    table.interrupt_recording('test_end')
    hand_id = stored_hands(path)[0]['hand_id']
    store.close()
    with sqlite3.connect(path) as connection:
        connection.execute('DROP TABLE IF EXISTS account_players')
        connection.execute('PRAGMA user_version=1')
    before = stored_hand(path, hand_id)
    store = HandStore(path)
    try:
        player_id = store.account_player_id(ISSUER, 'one')
        assert player_id == store.account_player_id(ISSUER, 'one')
        assert player_id != store.account_player_id(ISSUER, 'two')
        assert player_id != store.account_player_id('https://other.example', 'one')
        assert stored_hand(path, hand_id) == before
    finally:
        store.close()
    store = HandStore(path)
    try:
        assert store.account_player_id(ISSUER, 'one') == player_id
    finally:
        store.close()


def test_identity_store_failure_does_not_create_a_guest_or_room(account_server, monkeypatch):
    address, handler, store = account_server

    def unavailable(*args):
        raise sqlite3.OperationalError('private database detail')

    monkeypatch.setattr(store, 'account_player_id', unavailable)
    status, _, body = call(address, '/api/rooms', body={})
    assert status == 503
    assert b'private database detail' not in body
    assert not handler.sessions and not handler.rooms.rooms


def test_rename_updates_only_callers_seat_and_records_name_without_changing_id(account_server):
    address, handler, store = account_server
    _, _, payload = call(address, '/api/rooms', body={'name': '房主'})
    code = json.loads(payload)['room']['code']
    assert call(address, '/api/room/join', subject='account-two',
                body={'code': code, 'name': '朋友'})[0] == 200
    # A waiting member can rename before the host starts.
    assert call(address, '/api/player/name', subject='account-two',
                body={'name': ' 等待中的朋友 '})[0] == 200
    assert call(address, '/api/room/start', body={})[0] == 200
    room = next(iter(handler.rooms.rooms.values()))
    original = room.table.env.recorder.document()
    original_players = list(room.table.record_players)
    version = room.version
    with room.changed:
        room.event = {'pid': 0, 'type': 'DISCARD', 'tile': 0}
    status, _, payload = call(address, '/api/player/name', subject='account-two', body={
        'name': '新的朋友🌿', 'pid': 0, 'player_id': original_players[0]['player_id']})
    state = json.loads(payload)
    assert status == 200 and state['room']['members'][0]['name'] == '新的朋友🌿'
    assert state['room']['members'][3]['name'] == '房主'
    assert state['version'] == version + 1 and state['display_event'] is None
    assert room.table.env.recorder.document() == original
    assert room.table.record_players[0] == original_players[0]
    assert room.table.record_players[1]['player_id'] == original_players[1]['player_id']
    saved = stored_hand(store.path, original['hand_id'])
    assert saved['metadata']['players'][1]['name'] == '等待中的朋友'
    event = saved['metadata']['seat_events'][-1]
    assert event['name'] == '新的朋友🌿' and event['pid'] == 1
    assert event['player_id'] == original_players[1]['player_id']
    # Another browser with this account sees the same name; the host sees the rotated seat.
    assert json.loads(call(address, '/api/state', subject='account-two')[2])[
        'room']['members'][0]['name'] == '新的朋友🌿'
    assert json.loads(call(address, '/api/state')[2])['room']['members'][1][
        'name'] == '新的朋友🌿'
    for invalid in (None, '', '   ', 42, '壞\n名字'):
        assert call(address, '/api/player/name', subject='account-two',
                    body={'name': invalid})[0] == 400
    assert room.version == version + 1


def test_practice_rename_is_server_side_and_keeps_player_identity(account_server):
    address, _, store = account_server
    assert call(address, '/api/state')[0] == 200
    before = json.loads(call(address, '/api/start', body={})[2])
    original = stored_hand(store.path, stored_hands(store.path)[0]['hand_id'])
    status, _, payload = call(address, '/api/player/name', body={'name': '練習玩家'})
    after = json.loads(payload)
    assert status == 200 and after['player_name'] == '練習玩家'
    for key in ('hand', 'drawn', 'rivers', 'totals', 'phase', 'round'):
        assert before[key] == after[key]
    assert json.loads(call(address, '/api/state')[2])['player_name'] == '練習玩家'
    saved = stored_hand(store.path, original['hand_id'])
    assert saved['metadata']['seat_events'][-1]['player_id'] == original[
        'metadata']['players'][0]['player_id']
    assert json.loads(call(address, '/api/state', subject='account-two')[2])[
        'player_name'] == '玩家'
