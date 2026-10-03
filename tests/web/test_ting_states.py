"""Tenpai hints and declaring ting are independent states."""
import pytest

from app.web import WebTable
from app.web_rooms import WebRoom


def ting_table():
    table = WebTable(42, human_pids={0, 1, 2, 3})
    for player in table.env.players:
        player.hand = []
        player.drawn = None
        player.melds = []
        player.river = []
    table.env.players[0].hand = [0, 1, 2, 3, 4, 5, 9, 10, 11,
                                 18, 19, 20, 27, 27, 27, 28]
    table.env.players[0].drawn = 29
    table.env.turn = 0
    table.env.phase = 'TURN'
    return table


@pytest.mark.parametrize('declared', [False, True])
def test_waiting_hand_keeps_hints_with_or_without_declaration(declared):
    table = ting_table()
    action = next(a for a in table.snapshot()['legal_actions']
                  if a['type'] == ('TING' if declared else 'DISCARD') and a['from'] == 'drawn')
    table.apply(action, pid=0)
    state = table.snapshot()
    assert state['declared_ting'] is declared
    assert [wait['tile'] for wait in state['ting_waits']] == [28]
    assert table.snapshot(1)['ting_waits'] == [], 'never reveal another player\'s waits'


def test_breaking_waiting_hand_clears_hints_without_declaring():
    table = ting_table()
    table.apply({'type': 'DISCARD', 'tile': 27, 'from': 'hand'}, pid=0)
    state = table.snapshot()
    assert not state['declared_ting']
    assert state['ting_waits'] == []


def test_declared_player_can_only_discard_drawn_tile_or_win():
    table = ting_table()
    player = table.env.players[0]
    player.declared_ting = True
    player.hand = [0, 0, 0, 0]
    player.drawn = 9
    assert table.env.legal_actions(0) == [{'type': 'DISCARD', 'tile': 9, 'from': 'drawn'}]
    player.hand = [0, 1, 2, 3, 4, 5, 9, 10, 11, 18, 19, 20, 27, 27, 27, 28]
    player.drawn = 28
    assert {action['type'] for action in table.env.legal_actions(0)} == {'DISCARD', 'HU'}


@pytest.mark.parametrize('online', [False, True])
@pytest.mark.parametrize('declared,drawn,automatic', [
    (True, 29, True), (True, 28, False), (False, 29, False),
])
def test_auto_discard_only_after_declared_ting_without_win(
    monkeypatch, online, declared, drawn, automatic
):
    table = ting_table()
    player = table.env.players[0]
    player.declared_ting = declared
    player.drawn = drawn
    original_hand = list(player.hand)
    frames = []
    if online:
        clock = [100.]
        monkeypatch.setattr('app.web_rooms.time.monotonic', lambda: clock[0])
        room = WebRoom('1234ABCD', 'a', table)
        room.started = True
        room.ready_at = 101.
        with room.changed:
            room.tick(100.)
            assert player.river == []
            clock[0] = 101.
            room.tick(101.)
            room.tick(101.)  # Repeated scheduler ticks must not discard twice.
    else:
        table.advance(frames)
        table.advance(frames)
    assert player.hand == original_hand
    assert player.river == ([drawn] if automatic else [])
    if automatic:
        assert player.drawn is None
        assert table.snapshot()['declared_ting']
        assert [wait['tile'] for wait in table.snapshot()['ting_waits']] == [28]
        if online:
            assert room.event == {'pid': 0, 'type': 'DISCARD'}
        else:
            assert frames[0]['type'] == 'DISCARD'
    else:
        assert player.drawn == drawn
        if declared:
            assert any(a['type'] == 'HU' for a in table.env.legal_actions(0))
