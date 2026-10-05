"""Claim restrictions last for the intended turn and reject direct engine bypasses."""
from copy import deepcopy

import pytest

from domain import Mahjong16Env
from domain.rules import Ruleset


def claim_env(**options):
    env = Mahjong16Env(Ruleset(include_flowers=False, allow_hu=False,
                              randomize_seating_and_dealer=False, **options), seed=42)
    env.reset()
    for player in env.players:
        player.hand = []
        player.drawn = None
        player.melds = []
        player.river = []
    env.turn = 0
    env.phase = 'TURN'
    return env


@pytest.mark.parametrize('order', [[0, 1, 2, 3], [2, 0, 3, 1]])
def test_upstream_kong_is_forbidden_but_other_seats_can_kong(order):
    for offset in (1, 2, 3):
        env = claim_env()
        env.seating_order = order
        env._seat_index = {pid: index for index, pid in enumerate(order)}
        source, target = order[0], order[offset]
        env.turn = source
        env.players[source].hand = [1]
        env.players[target].hand = [1, 1, 1, 8]
        env.step({'type': 'DISCARD', 'tile': 1, 'from': 'hand'})
        actions = env.legal_actions(target)
        assert {'type': 'PONG'} in actions
        assert ({'type': 'GANG'} in actions) is (offset != 1)
        if offset == 1:
            before = deepcopy([p.as_dict() for p in env.players])
            with pytest.raises(AssertionError):
                env.step({'type': 'GANG'})  # Default reaction actor cannot bypass the rule.
            assert [p.as_dict() for p in env.players] == before
            assert env.claims == [] and env.reaction_responses == {}


@pytest.mark.parametrize('supplement', [False, True])
def test_pong_cannot_add_kong_until_next_normal_draw(supplement):
    env = claim_env()
    env.players[0].hand = [1]
    env.players[1].hand = [1, 1, 1, 8] + ([5] * 4 if supplement else [])
    env.step({'type': 'DISCARD', 'tile': 1, 'from': 'hand'})
    env.step({'type': 'PONG'}, pid=1)
    if supplement:
        env.step({'type': 'ANGANG', 'tile': 5})
        assert env.players[1].drawn is not None
    assert env.players[1].pong_waiting_draw
    assert {'type': 'KAKAN', 'tile': 1} not in env.legal_actions(1)
    before = deepcopy(env.players[1].as_dict())
    with pytest.raises(AssertionError):
        env.step({'type': 'KAKAN', 'tile': 1})
    assert env.players[1].as_dict() == before
    env.step({'type': 'DISCARD', 'tile': 8, 'from': 'hand'})
    while True:
        while env.phase == 'REACTION':
            env.step({'type': 'PASS'})
        if env.turn == 1:
            break
        assert env.players[1].pong_waiting_draw
        env.step({'type': 'DISCARD', 'tile': env.players[env.turn].drawn, 'from': 'drawn'})
    assert not env.players[1].pong_waiting_draw
    assert {'type': 'KAKAN', 'tile': 1} in env.legal_actions(1)


def test_chi_blocks_all_copies_for_one_discard_and_resets_next_hand():
    env = claim_env()
    env.players[0].hand = [2]
    env.players[1].hand = [0, 1, 2, 2, 3]
    env.step({'type': 'DISCARD', 'tile': 2, 'from': 'hand'})
    env.step({'type': 'CHI', 'use': [0, 1]}, pid=1)
    assert env._obs(1)['blocked_discards'] == [2]
    assert env._obs(0)['blocked_discards'] == []
    assert not any(a['type'] in ('DISCARD', 'TING') and a['tile'] == 2
                   for a in env.legal_actions(1))
    before = deepcopy(env.players[1].as_dict())
    for kind in ('DISCARD', 'TING'):
        with pytest.raises(AssertionError):
            env.step({'type': kind, 'tile': 2, 'from': 'hand'})
        assert env.players[1].as_dict() == before
    env.step({'type': 'DISCARD', 'tile': 3, 'from': 'hand'})
    assert env.players[1].chi_discard_lock is None
    assert 2 in env._legal_discards(1)
    env.players[1].chi_discard_lock = 2
    env.players[1].pong_waiting_draw = True
    env.reset()
    assert all(p.chi_discard_lock is None and not p.pong_waiting_draw for p in env.players)


def test_chi_excludes_an_otherwise_valid_ting_discard():
    candidate = {'type': 'TING', 'tile': 2, 'from': 'hand', 'waits': [27]}
    for allowed in (False, True):
        env = claim_env(allow_same_tile_discard_after_chi=allowed)
        env.players[0].hand = [2]
        env.players[1].hand = [0, 1, 2, 3, 3, 3, 6, 6, 6, 9, 9, 9, 12, 12, 12, 27]
        env.step({'type': 'DISCARD', 'tile': 2, 'from': 'hand'})
        env.step({'type': 'CHI', 'use': [0, 1]}, pid=1)
        assert (candidate in env.legal_actions(1)) is allowed


def test_restrictions_can_be_disabled_in_the_ruleset():
    env = claim_env(allow_upstream_gang=True, allow_immediate_kakan_after_pong=True,
                    allow_same_tile_discard_after_chi=True)
    env.players[0].hand = [1]
    env.players[1].hand = [1, 1, 1, 0, 2]
    env.step({'type': 'DISCARD', 'tile': 1, 'from': 'hand'})
    assert {'type': 'GANG'} in env.legal_actions(1)
    env.step({'type': 'PONG'}, pid=1)
    assert {'type': 'KAKAN', 'tile': 1} in env.legal_actions(1)
    env = claim_env(allow_same_tile_discard_after_chi=True)
    env.players[0].hand = [2]
    env.players[1].hand = [0, 1, 2, 3]
    env.step({'type': 'DISCARD', 'tile': 2, 'from': 'hand'})
    env.step({'type': 'CHI', 'use': [0, 1]}, pid=1)
    assert {'type': 'DISCARD', 'tile': 2, 'from': 'hand'} in env.legal_actions(1)
