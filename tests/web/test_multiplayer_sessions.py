"""Shared session summaries stay participant-only across seat changes."""
from tests.web.test_record_api import call, server


def test_both_players_share_room_session_statistics_and_replay(tmp_path):
    with server(tmp_path / 'hands.sqlite3') as (address, handler, store):
        cookies = []
        for _ in range(3):
            _, _, cookie = call(address, '/api/state')
            cookies.append(cookie.split(';')[0])
        host, guest, stranger = cookies
        _, state, _ = call(address, '/api/rooms', host, {'name': '房主'})
        code = state['room']['code']
        call(address, '/api/room/join', guest, {'code': code, 'name': '朋友'})
        call(address, '/api/room/start', host, {})
        room = handler.rooms.rooms[code]
        with room.changed:
            while not room.table.env.done:
                actor = room.table.actor()
                room.apply(room.table.bot.choose(room.table.env._obs(actor)),
                           pid=actor, source='bot')
        table_id = room.table.table_id
        details = []
        for cookie in (host, guest):
            _, result, _ = call(address, '/api/sessions', cookie)
            shared = next((item for item in result['sessions'] if item['id'] == table_id), None)
            assert shared is not None, 'multiplayer table must appear in Session records'
            assert shared['source'] == 'multiplayer' and shared['room_code'] == code
            assert shared['resumable'] and shared['completed_hands'] == 1
            status, detail, _ = call(address, '/api/session?session_id=' + table_id, cookie)
            assert status == 200
            assert detail['totals'] == room.table.totals
            assert detail['players'][:2] == ['房主', '朋友']
            assert len(detail['hands']) == 1 and len(detail['points']) == 2
            assert detail['hands'][0]['replayable']
            assert not {'setup', 'steps', 'recovery', 'initial_state'} & detail.keys()
            details.append(detail)
            status, replay, _ = call(address, '/api/replay?hand_id=' + shared['hand_id'], cookie)
            assert status == 200 and replay['frames'][-1]['state']['done']
            status, resumed, _ = call(address, '/api/resume', cookie,
                                      {'hand_id': shared['hand_id']})
            assert status == 200 and resumed['session_id'] == table_id
        assert details[0] == details[1]
        assert call(address, '/api/session?session_id=' + table_id, stranger)[0] == 400
        _, result, _ = call(address, '/api/sessions', stranger)
        assert all(item['id'] != table_id for item in result['sessions'])
        # Shared tables must not become the player's selected practice session.
        sid = host.partition('=')[2]
        assert store.selected_practice(handler.rooms.rooms[code].record_ids[sid]) != table_id
        # A later participant can see public table totals, but not earlier concealed hands.
        assert call(address, '/api/room/leave', guest, {})[0] == 200
        assert call(address, '/api/room/next', host, {})[0] == 200
        assert call(address, '/api/room/join', stranger,
                    {'code': code, 'name': '新朋友'})[0] == 200
        with room.changed:
            while not room.table.env.done:
                actor = room.table.actor()
                room.apply(room.table.bot.choose(room.table.env._obs(actor)),
                           pid=actor, source='bot')
        for cookie, playable in ((guest, [True, False]), (stranger, [False, True])):
            status, detail, _ = call(address, '/api/session?session_id=' + table_id, cookie)
            assert status == 200 and len(detail['hands']) == 2
            assert [hand['replayable'] for hand in detail['hands']] == playable
            assert detail['players'][1] == '新朋友'
            assert detail['hands'][0]['players'][1] == '朋友'
            assert detail['hands'][1]['players'][1] == '新朋友'
            for hand, allowed in zip(detail['hands'], playable):
                status, replay, _ = call(address, '/api/replay?hand_id=' + hand['id'], cookie)
                assert status == (200 if allowed else 400)
                if allowed:
                    expected = '朋友' if hand['round'] == 1 else '新朋友'
                    assert expected in replay['frames'][-1]['state']['replay_names']
            assert detail['resumable'] == (cookie == stranger)
        assert call(address, '/api/resume', guest,
                    {'hand_id': detail['hands'][-1]['id']})[0] == 400


def test_join_after_settlement_cannot_replay_but_can_continue_current_seat(tmp_path):
    with server(tmp_path / 'hands.sqlite3') as (address, handler, store):
        _, _, host = call(address, '/api/state')
        host = host.split(';')[0]
        _, _, late = call(address, '/api/state')
        late = late.split(';')[0]
        _, state, _ = call(address, '/api/rooms', host, {'name': '房主'})
        code = state['room']['code']
        call(address, '/api/room/start', host, {})
        room = handler.rooms.rooms[code]
        with room.changed:
            while not room.table.env.done:
                actor = room.table.actor()
                room.apply(room.table.bot.choose(room.table.env._obs(actor)),
                           pid=actor, source='bot')
        assert call(address, '/api/room/join', late,
                    {'code': code, 'name': '結算後才加入'})[0] == 200
        status, detail, _ = call(address, '/api/session?session_id=' + room.table.table_id, late)
        assert status == 200 and detail['completed_hands'] == 1
        assert not detail['hands'][0]['replayable'], 'post-settlement join is not hand participation'
        hand_id = detail['hand_id']
        assert call(address, '/api/replay?hand_id=' + hand_id, late)[0] == 400
        status, history, _ = call(address, '/api/history', late)
        assert status == 200 and all(hand['id'] != hand_id for hand in history['hands'])
        assert detail['resumable'], 'the current reserved seat can still continue the table'
        assert call(address, '/api/resume', late, {'hand_id': hand_id})[0] == 200


def test_unrelated_long_session_has_bounded_authorization_work(tmp_path):
    from contextlib import closing
    from copy import deepcopy

    from app.hand_store import HandStore
    from app.web import WebTable

    with closing(HandStore(tmp_path / 'hands.sqlite3')) as store:
        table = WebTable(seed=7, record_store=store, player_id='owner')
        template = table.env.recorder.document()
        metadata = deepcopy(table.env.recorder.metadata)
        metadata.update(source='multiplayer', table_id='long-shared-table')
        for index in range(80):
            document = deepcopy(template)
            document['hand_id'] = f'long-hand-{index}'
            metadata.update(started_at=f'2099-{index:04}', hand_index=index+1)
            store.save(document, metadata)
        steps = 0

        def budget():
            nonlocal steps
            steps += 1000
            return steps > 100_000

        # Bound database work rather than using a machine-dependent elapsed-time limit.
        store.connection.set_progress_handler(budget, 1000)
        try:
            assert store.session_hands('outsider', heads=True) == []
        finally:
            store.connection.set_progress_handler(None, 0)
