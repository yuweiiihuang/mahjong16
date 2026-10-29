"""Durable single-player sessions cannot discard a deal or rewind another session."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from app.hand_store import stored_hands
from domain.gameplay.recording import private_state
from tests.web.test_record_api import call, server


def finish(table):
    while not table.env.done:
        table.act(table.bot.choose(table.env._obs(0)))


def test_new_session_gate_switching_and_restart(tmp_path):
    path = tmp_path / 'hands.sqlite3'
    with server(path) as (address, handler, store):
        _, initial, cookie = call(address, '/api/state')
        cookie = cookie.split(';')[0]
        sid = cookie.partition('=')[2]
        first_id = initial['session_id']
        initial_private = private_state(handler.sessions[sid].env)
        assert call(address, '/api/new', cookie, {})[0] == 400
        assert private_state(handler.sessions[sid].env) == initial_private
        finish(handler.sessions[sid])
        first_totals = list(handler.sessions[sid].totals)
        _, result, _ = call(address, '/api/sessions', cookie)
        first = result['sessions'][0]
        assert first['id'] == first_id and first['established']
        # Concurrent requests may create only one new first hand.
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: call(address, '/api/new', cookie, {}), range(2)))
        assert sorted(response[0] for response in responses) == [200, 400]
        second = handler.sessions[sid]
        second_id = second.table_id
        second_private = private_state(second.env)
        assert second_id != first_id and second.totals == [1000] * 4
        assert len(stored_hands(path)) == 2
        action = next(a for a in second.snapshot()['legal_actions'] if a['type'] == 'DISCARD')
        assert call(address, '/api/action', cookie, action,
                    {'X-Qinghe-Session': first_id})[0] == 400
        assert private_state(second.env) == second_private
        # Return to finished A: unfinished B must still block creating C.
        assert call(address, '/api/resume', cookie, {'hand_id': first['hand_id']})[0] == 200
        assert call(address, '/api/new', cookie, {})[0] == 400
        _, result, _ = call(address, '/api/sessions', cookie)
        assert len(result['sessions']) == 2
        assert all(item['resumable'] for item in result['sessions'])
        b = next(item for item in result['sessions'] if item['id'] == second_id)
        assert not b['established'] and b['completed_hands'] == 0
        assert call(address, '/api/resume', cookie, {'hand_id': b['hand_id']})[0] == 200
        assert private_state(handler.sessions[sid].env) == second_private
        # Forgetting in-memory connections must not create a third session.
        handler.sessions.clear()
        handler.session_seen.clear()
        _, returned, _ = call(address, '/api/state', cookie)
        assert returned['session_id'] == second_id
        assert private_state(handler.sessions[sid].env) == second_private
        assert len(stored_hands(path)) == 2
        # Select A durably before a real process/store restart.
        assert call(address, '/api/resume', cookie, {'hand_id': first['hand_id']})[0] == 200
    with server(path) as (address, handler, store):
        cookie = f'qinghe_{address[1]}={sid}'  # Test server chooses a new port after restart.
        _, returned, _ = call(address, '/api/state', cookie)
        assert returned['session_id'] == first_id
        assert returned['totals'] == first_totals
        assert len(stored_hands(path)) == 2
        _, next_hand, _ = call(address, '/api/next', cookie, {})
        assert next_hand['session_id'] == first_id and next_hand['round'] == 2
        assert next_hand['totals'] == first_totals
        assert call(address, '/api/resume', cookie, {'hand_id': first['hand_id']})[0] == 400


def test_session_statistics_include_old_hands_draws_and_enforce_ownership(tmp_path):
    with server(tmp_path / 'hands.sqlite3') as (address, handler, store):
        _, initial, cookie = call(address, '/api/state')
        cookie = cookie.split(';')[0]
        sid = cookie.partition('=')[2]
        table = handler.sessions[sid]
        # Summary fixtures deliberately lack replay recovery. No fake engine prefix is replayed.
        template = table.env.recorder.document()
        metadata = deepcopy(table.env.recorder.metadata)
        table_id = 'long-summary-session'
        metadata['table_id'] = table_id
        totals = [1000] * 4
        for index in range(1, 103):
            document = deepcopy(template)
            document.update(hand_id=f'summary-{index}', status='completed', settlement={
                'winner': 0 if index <= 101 else None,
                'win_source': 'RON' if index <= 101 else None,
                'payments': [30, -30, 0, 0] if index <= 101 else [0] * 4,
                'tai': [1, 0, 0, 0],
            })
            before = list(totals)
            totals = [a + b for a, b in zip(totals, document['settlement']['payments'])]
            metadata.update(hand_index=index, started_at=f'2099-01-01T00:{index:03d}',
                            totals_before=before, totals_after=totals,
                            settlement={'payer': 1 if index <= 101 else None})
            metadata.pop('recovery', None)
            store.save(document, metadata)
        _, detail, _ = call(address, '/api/session?session_id=' + table_id, cookie)
        assert detail['completed_hands'] == 102 and detail['established']
        assert detail['draws'] == 1 and len(detail['hands']) == 102
        assert len(detail['points']) == 103
        assert detail['totals'] == [4030, -2030, 1000, 1000]
        assert detail['points'][0]['totals'] == [1000] * 4
        assert detail['points'][-1]['totals'] == detail['totals']
        assert detail['seats'][0]['wins'] == detail['seats'][0]['ron'] == 101
        assert detail['seats'][1]['deal_ins'] == 101
        assert detail['seats'][0]['net'] == 3030
        assert detail['seats'][0]['average_payment'] == 3030 / 102
        assert not detail['resumable']
        assert not {'setup', 'steps', 'recovery', 'initial_state'} & detail.keys()
        _, recent, _ = call(address, '/api/history', cookie)
        assert len(recent['hands']) == 100  # Different contract, never used for aggregates.
        _, sessions, _ = call(address, '/api/sessions', cookie)
        assert len(sessions['sessions']) == 2
        assert any(item['id'] == initial['session_id'] for item in sessions['sessions'])
        _, _, stranger = call(address, '/api/state')
        stranger = stranger.split(';')[0]
        assert call(address, '/api/session?session_id=' + table_id, stranger)[0] == 400
        _, strangers, _ = call(address, '/api/sessions', stranger)
        assert all(item['id'] != table_id for item in strangers['sessions'])
        # A first zero-payment draw establishes a session even without a changed score.
        draw = deepcopy(document)
        draw['hand_id'] = 'draw-only'
        metadata.update(table_id='draw-session', hand_index=1,
                        totals_before=[1000] * 4, totals_after=[1000] * 4)
        store.save(draw, metadata)
        _, draw_session, _ = call(address, '/api/session?session_id=draw-session', cookie)
        assert draw_session['established'] and draw_session['completed_hands'] == 1
        assert draw_session['totals'] == [1000] * 4 and draw_session['draws'] == 1
