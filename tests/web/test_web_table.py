"""Regression tests for browser action validation and private observations."""
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
    assert result['done'] or result['actor'] == 0
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
