"""Regression tests for browser action validation and private observations."""
import json

import pytest
from app.web import WebTable


def test_start_and_advance_to_human():
    table = WebTable(seed=42)
    state = table.snapshot()
    assert state['actor'] == 0
    assert len(state['hand']) == 16
    assert state['drawn'] is not None
    action = next(a for a in state['legal_actions'] if a['type'] == 'DISCARD')
    result = table.act(action)
    assert result['done'] or table.actor() == 0
    assert result['actor'] == (None if result['done'] or result['phase'] == 'REACTION' else 0)
    assert result['rivers'][0] or result['players'][1]['melds']
    assert all('hand' not in player for player in result['players'])


def test_reject_forged_action_without_mutation():
    table = WebTable(seed=42)
    before = table.snapshot()
    with pytest.raises(ValueError):
        table.act({'type': 'HU'})
    assert table.snapshot() == before


def test_whole_round_terminates_with_only_legal_moves():
    table = WebTable(seed=12)
    for _ in range(200):
        if table.env.done:
            break
        action = table.bot.choose(table.env._obs(0))
        table.act(action)
    assert table.env.done
    assert table.snapshot()['legal_actions'] == []


def test_playback_is_ordered_immutable_and_does_not_change_gameplay():
    table, control = WebTable(42), WebTable(42)
    for _ in range(12):
        if table.env.done:
            break
        action = table.bot.choose(table.env._obs(0))
        result = table.act(action)
        control.apply(action)
        control.advance()
        assert {k: v for k, v in result.items() if k != 'playback'} == control.snapshot()
        frames = result['playback']
        assert all(frame['type'] != 'PASS' for frame in frames)
        assert all(frame['state']['legal_actions'] == [] for frame in frames)
        assert [len(f['state']['events']) for f in frames] == sorted(
            len(f['state']['events']) for f in frames
        )
        for frame in frames:
            if frame['type'] == 'THINK':
                assert frame['state']['phase'] == 'TURN'
                assert frame['state']['actor'] == frame['pid']
            if frame['type'] in ('CHI', 'PONG', 'GANG'):
                assert frame['state']['players'][frame['pid']]['melds'][-1]['type'] == frame['type']
        if frames:
            saved = json.dumps(frames)
            table.snapshot()['players'][0]['melds'].append({'type': 'PONG', 'tiles': [0, 0, 0]})
            assert json.dumps(frames) == saved
            assert table.env.players[0].melds == control.env.players[0].melds


def test_playback_redacts_concealed_kongs_and_bot_waits_without_mutating_engine():
    table = WebTable(42)
    table.env.players[1].melds = [{'type': 'ANGANG', 'tiles': [0] * 4}]
    table.events = [{'pid': 1, 'type': 'ANGANG', 'tile': 0},
                    {'pid': 2, 'type': 'TING', 'tile': 9, 'waits': [1, 2]}]
    frames = []
    table.record_frame(frames, 1, 'THINK')
    state = frames[0]['state']
    assert state['players'][1]['melds'][0]['tiles'] == [None] * 4
    assert state['melds_all'][1][0]['tiles'] == [None] * 4
    assert 'tile' not in state['events'][0]
    assert 'waits' not in state['events'][1]
    assert table.env.players[1].melds[0]['tiles'] == [0] * 4
    assert table.events[0]['tile'] == 0
    assert table.events[1]['waits'] == [1, 2]
