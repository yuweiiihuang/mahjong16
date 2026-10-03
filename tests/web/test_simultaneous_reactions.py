"""Discard reactions accept private choices in any arrival order."""
from copy import deepcopy
from itertools import permutations
import threading

import pytest

from app.web import WebTable
from app.web_rooms import WebRoom


def reaction_table(human_pids=None, hu=False):
    table = WebTable(42, human_pids={0, 1, 2, 3} if human_pids is None else human_pids)
    env = table.env
    for player in env.players:
        player.hand = []
        player.drawn = None
        player.melds = []
        player.river = []
    env.players[0].hand = [1]
    env.players[1].hand = [0, 2]
    env.players[2].hand = [1, 1]
    if hu:
        env.players[3].hand = [1]
        env.players[3].melds = [
            {'type': 'PONG', 'tiles': [tile] * 3, 'from_pid': 0}
            for tile in (3, 6, 9, 12, 18)
        ]
    env.turn = 0
    env.phase = 'TURN'
    env.done = False
    env.step({'type': 'DISCARD', 'tile': 1, 'from': 'hand'})
    table.events = []
    return table


@pytest.mark.parametrize('order', list(permutations((1, 2, 3))))
@pytest.mark.parametrize('hu', [False, True])
def test_arrival_order_never_changes_claim_priority(order, hu):
    table = reaction_table(hu=hu)
    env = table.env
    choices = {1: {'type': 'CHI', 'use': [0, 2]}, 2: {'type': 'PONG'},
               3: {'type': 'HU' if hu else 'PASS'}}
    before = deepcopy([(player.hand, player.melds) for player in env.players])
    for index, pid in enumerate(order):
        table.apply(choices[pid], pid=pid)
        if index < 2:
            assert env.phase == 'REACTION'
            assert table.events == []
            assert [(player.hand, player.melds) for player in env.players] == before
            assert env.legal_actions(pid) == []
            assert env.legal_actions(0) == []
            with pytest.raises(AssertionError):
                env.step(choices[pid], pid=pid)
    assert table.events[-1]['type'] == ('HU' if hu else 'PONG')
    assert table.events[-1]['pid'] == (3 if hu else 2)


@pytest.mark.parametrize('first', [1, 2])
def test_room_replies_share_revision_and_only_sender_sees_choice(first):
    table = reaction_table()
    room = WebRoom('ABCD1234', 'a', table)
    with room.changed:
        for sid in ('b', 'c', 'd'):
            room.join(sid)
        room.started = True
        table.advance()  # Seat 3 has no choice and passes automatically.
        version = room.version
        observer = deepcopy(room.snapshot('a'))
        second = 3 - first
        other = deepcopy(room.snapshot(room.seats[second]))
        choices = {1: {'type': 'CHI', 'use': [0, 2]}, 2: {'type': 'PONG'}}
        assert choices[1] in room.snapshot('b')['legal_actions']
        assert choices[2] in room.snapshot('c')['legal_actions']
        room.act(room.seats[first], version, 'first', choices[first])
        assert room.version == version
        assert room.snapshot('a') == observer
        assert room.snapshot(room.seats[second]) == other
        own = room.snapshot(room.seats[first])
        assert own['reaction_choice'] == choices[first]
        assert own['legal_actions'] == []
        assert choices[first] in own['reaction_actions']
        assert {'type': 'PASS'} in own['reaction_actions']
        room.act(room.seats[first], version, 'first', choices[first])  # Retry is harmless.
        with pytest.raises(ValueError):
            room.act(room.seats[first], version, 'change-choice', {'type': 'PASS'})
        room.act(room.seats[second], version, 'second', choices[second])
        assert room.version == version + 1
        assert table.events == [{'pid': 2, 'type': 'PONG', 'tile': 1, 'from_pid': 0}]
        assert room.snapshot('b')['reaction_choice'] is None
        with pytest.raises(ValueError):
            room.act('b', version, 'late', choices[1])


def test_practice_bots_decide_before_human_and_do_not_wait_for_chi():
    table = reaction_table(human_pids={1})
    calls = []

    def choose(obs):
        calls.append(obs['player'])
        return {'type': 'PONG' if obs['player'] == 2 else 'PASS'}

    table.bot.choose = choose
    table.advance()
    assert calls == [2, 3]
    assert table.env.pending_reactions() == [1]
    assert table.env.reaction_responses[2] == {'type': 'PONG'}
    assert table.events == []


def test_room_bot_can_reply_while_earlier_human_is_still_deciding():
    table = reaction_table()
    room = WebRoom('ABCD1234', 'a', table)
    with room.changed:
        room.join('b')
        room.started = True
        table.advance()
        room.table.bot.choose = lambda obs: {'type': 'PONG'}
        room.tick(room.seen['a'])
        assert table.env.pending_reactions() == [1]
        assert table.env.reaction_responses[2] == {'type': 'PONG'}
        assert table.events == []


def test_one_player_can_choose_pong_without_first_declining_hu():
    table = reaction_table()
    env = table.env
    env.players[2].hand = [3, 3, 0, 0]
    env.players[2].melds = [
        {'type': 'PONG', 'tiles': [tile] * 3, 'from_pid': 0}
        for tile in (6, 9, 12, 18)
    ]
    # The discard completes a triplet; the player can either win or call that triplet.
    env.last_discard['tile'] = 3
    env.players[0].river = [3]
    actions = env.legal_actions(2)
    assert {'type': 'HU'} in actions
    assert {'type': 'PONG'} in actions
    env.step({'type': 'PONG'}, pid=2)
    env.step({'type': 'PASS'}, pid=1)
    _, _, _, info = env.step({'type': 'PASS'}, pid=3)
    assert info['resolved_claim']['type'] == 'PONG'


def test_two_hu_claims_use_seat_distance_instead_of_arrival_order():
    table = reaction_table(hu=True)
    env = table.env
    env.players[2].hand = [1]
    env.players[2].melds = [
        {'type': 'PONG', 'tiles': [tile] * 3, 'from_pid': 0}
        for tile in (21, 24, 27, 28, 29)
    ]
    env.step({'type': 'HU'}, pid=3)
    env.step({'type': 'HU'}, pid=2)
    assert not env.done
    env.step({'type': 'PASS'}, pid=1)
    assert env.winner == 2


def test_two_concurrent_seats_can_reply_from_the_same_snapshot():
    table = reaction_table()
    room = WebRoom('ABCD1234', 'a', table)
    with room.changed:
        room.join('b')
        room.join('c')
        room.started = True
        table.advance()
    version = room.version
    barrier = threading.Barrier(2)
    errors = []

    def reply(sid, action):
        barrier.wait()
        try:
            with room.changed:
                room.act(sid, version, sid, action)
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=reply, args=('b', {'type': 'CHI', 'use': [0, 2]})),
               threading.Thread(target=reply, args=('c', {'type': 'PONG'}))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert errors == []
    assert table.events[-1]['pid'] == 2
    assert table.events[-1]['type'] == 'PONG'


def test_all_passes_draw_once_only_after_last_reply():
    table = reaction_table()
    env = table.env
    wall_size = len(env.wall)
    for pid in (3, 1):
        env.step({'type': 'PASS'}, pid=pid)
        assert len(env.wall) == wall_size
        assert env.phase == 'REACTION'
    env.step({'type': 'PASS'}, pid=2)
    assert env.phase == 'TURN' and env.turn == 1
    assert len(env.wall) == wall_size - 1


@pytest.mark.parametrize('discarder', [1, 2])
def test_non_upstream_chi_shape_only_auto_passes(discarder):
    table = WebTable(42, human_pids={0, 1, 2, 3})
    env = table.env
    for player in env.players:
        player.hand = []
        player.drawn = None
        player.melds = []
        player.river = []
    env.players[0].hand = [0, 2]  # Could chi tile 1 only from upstream seat 3.
    env.players[discarder].hand = [1]
    env.players[3].hand = [1, 1]  # Keep the reaction window open for a real choice.
    env.turn = discarder
    env.phase = 'TURN'
    env.step({'type': 'DISCARD', 'tile': 1, 'from': 'hand'})
    assert env.legal_actions(0) == [{'type': 'PASS'}]
    table.advance()
    state = table.snapshot(0)
    assert state['reaction_choice'] == {'type': 'PASS'}
    assert state['reaction_actions'] == [{'type': 'PASS'}]
    assert state['legal_actions'] == []
