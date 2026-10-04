"""Online-room privacy, concurrency, reconnect and actual HTTP contracts."""
import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from app.web import WebHandler, WebTable
from app.web_rooms import RoomRegistry, WebRoom


@pytest.fixture
def room(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('app.web_rooms.time.monotonic', lambda: clock[0])
    room = WebRoom('1234ABCD', 'a', WebTable(42, human_pids={0, 1, 2, 3}))
    with room.changed:
        for sid in ('b', 'c', 'd'):
            room.join(sid)
        room.start('a')
        clock[0] += 1
        room.tick(clock[0])
    return room, clock


def test_each_player_gets_only_own_hand_and_correct_relative_seats(room):
    room, _ = room
    env = room.table.env
    env.players[1].melds = [{'type': 'ANGANG', 'tiles': [8] * 4, 'from_pid': None}]
    room.table.events = [{'pid': 1, 'type': 'ANGANG', 'tile': 8},
                         {'pid': 1, 'type': 'TING', 'tile': 0, 'waits': [3, 4]}]
    for viewer, sid in enumerate(('a', 'b', 'c', 'd')):
        state = room.snapshot(sid)
        assert state['hand'] == env.players[viewer].hand
        assert state['drawn'] == env.players[viewer].drawn
        assert state['player'] == 0
        assert state['dealer'] == (env.dealer_pid - viewer) % 4
        assert state['actor'] == (room.table.actor() - viewer) % 4
        assert bool(state['legal_actions']) == (viewer == room.table.actor())
        assert 'live_public' not in state
        assert all('hand' not in player for player in state['players'])
        kong = state['players'][(1 - viewer) % 4]['melds'][0]
        assert kong['tiles'] == ([8] * 4 if viewer == 1 else [None] * 4)
        if viewer != 1:
            assert 'tile' not in state['events'][0]
            assert 'waits' not in state['events'][1]
    assert env.players[1].melds[0]['tiles'] == [8] * 4


def test_stale_wrong_seat_and_duplicate_actions(room):
    room, _ = room
    action = room.table.env.legal_actions(0)[0]
    with room.changed:
        before = room.snapshot('a')
        with pytest.raises(ValueError):
            room.act('b', room.version, 'wrong-seat', action)
        with pytest.raises(ValueError):
            room.act('a', room.version - 1, 'stale', action)
        assert room.snapshot('a') == before
        version = room.version
        room.act('a', version, 'once', action)
        applied = room.snapshot('a')
        room.act('a', version, 'once', action)
        assert room.snapshot('a') == applied


def test_reaction_actor_is_private_but_all_pending_seats_keep_legal_controls(room):
    room, _ = room
    env = room.table.env
    env.phase = 'REACTION'
    env.reaction_queue = [1, 2, 3]
    env.reaction_idx = 1
    env.last_discard = {'pid': 0, 'tile': 1}
    env.players[2].hand = [1, 1]
    env.players[3].hand = [1, 1]
    for pid, sid in enumerate(('a', 'b', 'c', 'd')):
        state = room.snapshot(sid)
        assert state['actor'] is None
        assert state['last_discard']['pid'] == (0 - pid) % 4
        if pid in (2, 3):
            assert {'type': 'PONG'} in state['legal_actions']
        else:
            assert state['legal_actions'] == []
    assert room.table.actor() == 2  # Sequential clients still have a default seat.


def test_tentative_and_rejected_claims_never_reveal_hand_tiles(room):
    room, _ = room
    table = room.table
    env = table.env
    env.phase = 'REACTION'
    env.reaction_queue = [1, 2, 3]
    env.reaction_idx = 0
    env.last_discard = {'pid': 0, 'tile': 1}
    env.players[0].river = [1]
    env.players[1].hand = [0, 2]
    env.players[2].hand = [1, 1]
    env.players[3].hand = []
    table.apply({'type': 'CHI', 'use': [0, 2]})
    assert room.snapshot('a')['events'] == []
    table.apply({'type': 'PONG'})
    assert room.snapshot('a')['events'] == []
    table.apply({'type': 'PASS'})
    assert table.events == [{'pid': 2, 'type': 'PONG', 'tile': 1, 'from_pid': 0}]
    assert room.snapshot('b')['events'] == [
        {'pid': 1, 'type': 'PONG', 'tile': 1, 'from_pid': 3}]


def test_concurrent_moves_apply_exactly_once(room):
    room, _ = room
    action, version = room.table.env.legal_actions(0)[0], room.version
    barrier = threading.Barrier(2)
    accepted = []

    def move(request_id):
        barrier.wait()
        with room.changed:
            try:
                room.act('a', version, request_id, action)
                accepted.append(request_id)
            except ValueError:
                pass

    threads = [threading.Thread(target=move, args=(str(i),)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(accepted) == 1


@pytest.mark.parametrize('seed', [12, 42, 99])
def test_four_players_complete_round_with_engine_parity_and_rotated_payments(seed):
    room = WebRoom('1234ABCD', 'a', WebTable(seed, human_pids={0, 1, 2, 3}))
    control = WebTable(seed, human_pids={0, 1, 2, 3})
    with room.changed:
        for sid in ('b', 'c', 'd'):
            room.join(sid)
        # Both use the same seeded hand; start does a fresh deal in normal play.
        room.started = True
        for index in range(1000):
            if room.table.env.done:
                break
            room.ready_at = 0
            pid = room.table.actor()
            action = room.table.bot.choose(room.table.env._obs(pid))
            room.act(room.seats[pid], room.version, str(index), action)
            control.apply(action)
            control.advance(auto_discard_ting=False)
            assert room.table.snapshot() == control.snapshot()
        assert room.table.env.done
        payments = room.table.settlement['payments']
        for viewer, sid in enumerate(room.seats):
            state = room.snapshot(sid)
            assert state['settlement']['payments'] == payments[viewer:] + payments[:viewer]
        totals = list(room.table.totals)
        room.table.settle()
        assert room.table.totals == totals
        with pytest.raises(ValueError):
            room.start('b', next_hand=True)
        room.start('a', next_hand=True)
        assert room.table.round == 2 and room.table.totals == totals


def test_shared_bot_delay_and_reconnect_grace(room):
    room, clock = room
    with room.changed:
        # A dropped player retains the seat; bot only starts after grace expires.
        clock[0] += 88
        room.tick(clock[0])
        assert room.table.events == []
        clock[0] += 3
        room.tick(clock[0])
        assert room.event == {'pid': 0, 'type': 'THINK'}
        assert room.snapshot('b')['display_event'] == {'pid': 3, 'type': 'THINK'}
        clock[0] += .3
        room.tick(clock[0])
        assert room.table.events == []
        room.join('a')  # Same identity resumes the same seat, even after a page reload.
        clock[0] += 1
        room.tick(clock[0])
        assert room.table.events == []
        assert room.snapshot('a')['legal_actions']
        clock[0] += 91
        room.tick(clock[0])
        assert room.table.events  # Bot now takes exactly one legal step.


def test_registry_room_capacity_join_lock_and_host_transfer():
    registry = RoomRegistry()
    room = registry.create('a', WebTable)
    for sid in ('b', 'c', 'd'):
        assert registry.join(sid, room.code) is room
    with pytest.raises(ValueError):
        registry.join('e', room.code)
    with room.changed:
        room.start('a')
        with pytest.raises(ValueError):
            room.join('e')
    registry.leave('b')
    assert room.owner == 'a'
    registry.leave('a')
    assert room.owner == 'c'
    names = [member['name'] for member in room.snapshot('c')['room']['members']]
    assert '你' not in names and '玩家 3' in names and '電腦玩家' in names
    with pytest.raises(ValueError):
        registry.get('a')


@pytest.mark.parametrize('finished', [False, True])
def test_disconnected_host_transfers_to_online_member_without_losing_seat(room, finished):
    room, clock = room
    with room.changed:
        if finished:
            room.table.env.done = True
            room.table.env.winner = None
            room.table.settle()
        clock[0] += 88
        room.touch('b')
        room.tick(clock[0])
        assert room.owner == 'a'  # Still within reconnect grace.
        clock[0] += 2
        room.touch('b')
        room.tick(clock[0])
        assert room.owner == 'b' and room.snapshot('b')['room']['host']
        assert room.seats[0] == 'a'
        room.join('a')
        assert room.owner == 'b' and not room.snapshot('a')['room']['host']
        if finished:
            room.start('b', next_hand=True)
            assert not room.table.env.done and room.table.round == 2


@pytest.fixture
def online_server():
    class Handler(WebHandler):
        sessions = {}
        session_seen = {}
        rooms = RoomRegistry()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    stop = threading.Event()
    scheduler = threading.Thread(target=Handler.rooms.run, args=(stop,), daemon=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    scheduler.start()
    thread.start()
    yield server.server_address, Handler
    stop.set()
    server.shutdown()
    server.server_close()
    scheduler.join(timeout=2)
    thread.join(timeout=2)


def test_http_invites_cookie_seat_auth_and_long_poll(online_server):
    address, handler = online_server

    def request(path, body=None, cookie='', origin=None):
        connection = http.client.HTTPConnection(*address, timeout=3)
        headers = {'Content-Type': 'application/json', 'Cookie': cookie}
        if origin:
            headers['Origin'] = origin
        connection.request('GET' if body is None else 'POST', path,
                           None if body is None else json.dumps(body), headers)
        response = connection.getresponse()
        payload = response.read()
        result = (json.loads(payload) if response.getheader('Content-Type', '').startswith(
            'application/json') else None)
        new_cookie = response.getheader('Set-Cookie', cookie).split(';')[0]
        status = response.status
        connection.close()
        return status, result, new_cookie

    status, state, host = request('/api/rooms', {'name': '麻雀雖小'})
    assert status == 200 and state['room']['host']
    assert state['room']['members'][0]['name'] == '麻雀雖小'
    assert state['hand'] == [] and state['drawn'] is None
    code = state['room']['code']
    cookies = [host]
    for index in range(3):
        status, guest, cookie = request('/api/room/join',
                                       {'code': code, 'name': f'碰碰胡椒粉{index}'})
        assert status == 200 and not guest['room']['host']
        assert guest['room']['members'][0]['name'] == f'碰碰胡椒粉{index}'
        cookies.append(cookie)
    assert len(set(cookies)) == 4
    assert state['auto_ting_discard'] is True
    status, preference, _ = request('/api/preferences', {'auto_ting_discard': False}, cookies[1])
    assert status == 200 and preference['auto_ting_discard'] is False
    assert request('/api/room/state', cookie=host)[1]['auto_ting_discard'] is True
    assert request('/api/preferences', {'auto_ting_discard': 'false'}, cookies[1])[0] == 400
    assert request('/api/preferences', {'auto_ting_discard': True}, cookies[1])[1]['auto_ting_discard']
    assert len(handler.sessions) == 4
    assert host.startswith(f'qinghe_{address[1]}=')
    assert request('/api/room/name', {'name': '海底撈月餅'}, cookies[1])[0] == 404
    resumed = request('/api/room/join', {'code': code, 'name': '改名'}, cookies[1])[1]
    assert resumed['room']['members'][0]['name'] == '碰碰胡椒粉0'
    host_state = request('/api/room/state', cookie=host)[1]
    assert host_state['room']['members'][1]['name'] == '碰碰胡椒粉0'
    assert host_state['room']['members'][0]['name'] == '麻雀雖小'
    assert request('/api/room/name', {'name': '冒名'}, 'forged=seat')[0] == 404
    assert request('/api/room/start', {}, cookies[1])[0] == 400
    assert request('/api/room/start', {}, host, 'https://evil.example')[0] == 400
    assert request('/api/room/start', {}, host)[0] == 200
    assert request('/api/room/name', {'name': '改名'}, host)[0] == 404
    status, state, _ = request('/api/room/state', cookie=host)
    assert status == 200
    # Scheduler publishes when the opening delay ends, waking the pending request.
    _, state, _ = request(f"/api/room/state?after={state['version']}", cookie=host)
    assert state['legal_actions']
    action = state['legal_actions'][0]
    payload = {'version': state['version'], 'request_id': 'http-move', 'action': action}
    assert request('/api/room/action', payload, cookies[1])[0] == 400
    assert request('/api/room/action', payload, host)[0] == 200
    assert request('/api/state', cookie=cookies[1])[1]['room']['code'] == code
    room = handler.rooms.get(host.split('=')[1])
    assert request('/api/room/action', payload, host)[0] == 200
    assert request('/api/room/state', cookie='table=forged')[0] == 400
    # Independent cookie survives reconnect; the same viewer receives the same hand.
    for cookie in cookies:
        status, state, _ = request('/api/room/state', cookie=cookie)
        assert status == 200 and state['player'] == 0
    assert request('/api/room/leave', {}, cookies[3])[0] == 200


def test_names_are_consistent_across_viewers_and_reconnects():
    registry = RoomRegistry()
    room = registry.create('host', WebTable, ' 麻雀雖小 ')
    registry.join('guest', room.code, '海底撈月餅')
    assert room.snapshot('host')['room']['members'][1]['name'] == '海底撈月餅'
    assert room.snapshot('guest')['room']['members'][0]['name'] == '海底撈月餅'
    registry.join('guest', room.code, '改名')
    assert room.seats.count('guest') == 1
    assert room.names['guest'] == '海底撈月餅'
    with room.changed:
        assert room.names['host'] == '麻雀雖小'
        room.start('host')
        version = room.version
        room.join('guest', '重新改名')
        assert room.version == version
        assert room.snapshot('host')['room']['members'][1]['name'] == '海底撈月餅'
    registry.leave('guest')
    assert 'guest' not in room.names


@pytest.mark.parametrize('name', [None, [], 1, '字' * 21, '玩家\n名稱', '玩家\x00'])
def test_invalid_names_do_not_reserve_seats_or_replace_existing_names(name):
    registry = RoomRegistry()
    with pytest.raises(ValueError):
        registry.create('invalid', WebTable, name)
    assert not registry.rooms and not registry.memberships
    room = registry.create('host', WebTable, '麻雀雖小')
    with pytest.raises(ValueError):
        registry.join('guest', room.code, name)
    assert room.seats == ['host', None, None, None]
    assert 'guest' not in registry.memberships
    with pytest.raises(ValueError):
        registry.join('host', room.code, name)
    assert room.names['host'] == '麻雀雖小'


def test_lobby_hides_all_tiles_and_drawn_flags_for_every_viewer():
    room = WebRoom('1234ABCD', 'host', WebTable(42, human_pids={0, 1, 2, 3}))
    with room.changed:
        for sid in ('guest1', 'guest2', 'guest3'):
            room.join(sid)
    room.table.env.players[0].drawn = 8
    for sid in room.seats:
        state = room.snapshot(sid)
        assert state['hand'] == [] and state['drawn'] is None
        assert all(player['count'] == 0 and not player['has_drawn']
                   for player in state['players'])
    assert room.table.env.players[0].drawn == 8
    with room.changed:
        room.start('host')
    for sid in room.seats:
        state = room.snapshot(sid)
        assert state['room']['started']
        assert state['players'][0]['count'] > 0
        assert state['players'][0]['has_drawn'] == (state['drawn'] is not None)
