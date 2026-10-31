"""AI display follows recorded decisions, not later preferences or guessed legacy levels."""
from copy import deepcopy
import json

from app.ai_history import seat_ai_history
from tests.web.test_record_api import call, server
from tests.web.test_practice_sessions import finish


def test_actual_controller_segments_fallback_and_missing_strategy():
    hand = {'status': 'completed', 'ai_levels': ['standard', 'advanced', 'standard', 'standard'],
            'step_count': 10, 'ai_failures': [{'pid': 1, 'reason': 'TimeoutError', 'after_seq': 7}],
            'decisions': [
                {'pid': 0, 'seq': 1, 'source': 'human', 'player_id': 'private-player'},
                {'pid': 1, 'seq': 2, 'source': 'bot', 'strategy': 'meowcats_2000'},
                {'pid': 1, 'seq': 5, 'source': 'human'},
                {'pid': 1, 'seq': 8, 'source': 'bot', 'strategy': 'greedy'},
                {'pid': 2, 'seq': 9, 'source': 'bot', 'strategy': 'greedy'},
                {'pid': 3, 'seq': 4, 'source': 'auto_pass'}]}
    original = deepcopy(hand)
    usage = seat_ai_history(hand)
    assert not usage[0]['used'] and not usage[3]['used']
    assert usage[1]['configured'] == 'advanced' and usage[1]['level'] == 'standard'
    assert usage[1]['degraded'] and usage[1]['fallback_after'] == 7
    assert usage[1]['fallback_reason'] == 'timeout' and usage[1]['mixed']
    assert [s['controller'] for s in usage[1]['segments']] == ['bot', 'human', 'bot']
    assert [s['start'] for s in usage[1]['segments']] == [2, 5, 8]
    assert usage[2]['used'] and usage[2]['level'] == 'standard'
    assert 'private-player' not in json.dumps(usage) and hand == original
    hand['status'] = 'active'
    assert all(not item['segments'] and item['fallback_after'] is None
               for item in seat_ai_history(hand))
    hand.update(ai_levels=None, ai_failures=None, decisions=None)
    assert all(item['used'] is None and item['level'] == 'unknown'
               for item in seat_ai_history(hand))
    hand['decisions'] = [{'pid': 1, 'seq': 2, 'source': 'bot'}]
    assert seat_ai_history(hand)[1]['level'] == 'unknown'


def test_session_ai_uses_hand_metadata_and_actual_decisions(tmp_path):
    with server(tmp_path / 'hands.sqlite3') as (address, handler, store):
        _, _, cookie = call(address, '/api/state')
        cookie = cookie.split(';')[0]
        table = handler.sessions[cookie.partition('=')[2]]
        finish(table)
        document = table.env.recorder.document()
        metadata = deepcopy(table.env.recorder.metadata)
        # Summary fixture models a recorded failure; no native search is asserted here.
        metadata['ai_levels'] = ['standard', 'advanced', 'standard', 'standard']
        decisions = [d for d in metadata['decisions'] if d['pid'] == 1 and d['source'] == 'bot']
        assert len(decisions) >= 2
        decisions[0]['strategy'] = 'meowcats_2000'
        metadata['ai_failures'] = [{'pid': 1, 'reason': 'capacity',
                                    'after_seq': decisions[0]['seq']}]
        metadata['recovery']['ai_levels'] = ['standard'] * 4
        store.save(document, metadata)
        status, detail, _ = call(address, '/api/session?session_id=' + table.table_id, cookie)
        assert status == 200
        usage = detail['hands'][0]['ai'][1]
        assert usage['configured'] == 'advanced' and usage['level'] == 'standard'
        assert usage['degraded'] and usage['fallback_reason'] == 'busy'
        assert detail['points'][1]['ai'] == detail['hands'][0]['ai']
        assert detail['ai'] == detail['hands'][0]['ai']
        assert 'player_id' not in json.dumps(detail)


def test_legacy_web_bot_decisions_use_the_original_fixed_standard_policy():
    for source in ('practice', 'multiplayer'):
        hand = {'status': 'completed', 'source': source, 'ai_levels': None,
                'ai_failures': None, 'step_count': 3,
                'decisions': [{'pid': 0, 'seq': 1, 'source': 'human'},
                              {'pid': 1, 'seq': 2, 'source': 'bot'},
                              {'pid': 2, 'seq': 3, 'source': 'bot', 'strategy': 'future_ai'}]}
        original = deepcopy(hand)
        usage = seat_ai_history(hand)
        assert usage[1]['used'] and usage[1]['level'] == 'standard'
        assert usage[1]['segments'][0]['level'] == 'standard'
        assert usage[0]['used'] is False
        assert usage[2]['level'] == 'unknown' and usage[3]['used'] is None
        assert hand == original, 'legacy compatibility must not rewrite stored records'
        # New-format missing strategy and unrelated exports must remain unknown.
        hand['ai_levels'] = ['standard'] * 4
        assert seat_ai_history(hand)[1]['level'] == 'unknown'
        hand.update(ai_levels=None, source='external')
        assert seat_ai_history(hand)[1]['level'] == 'unknown'
