"""Wire privacy, host legality and owned-process failure boundaries."""
from copy import deepcopy
import os
from pathlib import Path
import sys

import pytest

from app.training_export import player_observation
from bots.meowcats import MeowCaTSStrategy, _request
from domain.gameplay.game_env import MahjongEnvironment
from domain.rules.ruleset import Ruleset


def state(flowers=False):
    rules = Ruleset(include_flowers=flowers)
    env = MahjongEnvironment(rules, seed=6202601)
    env.reset()
    obs = player_observation(env, env.turn)
    obs['melds_all'] = [p['melds'] for p in obs['players']]
    return rules, env, obs


def test_wire_counts_and_real_hidden_state_invariance():
    rules, env, obs = state()
    line, actions = _request(obs, rules, 1)
    tokens = list(map(int, line.split()))
    hand = obs['hand'] + [obs['drawn']]
    assert tokens[:4] == [1, 1, 0, obs['n_remaining'] - rules.dead_wall_base]
    assert tokens[4:38] == [hand.count(t) for t in range(34)]
    assert tokens[38] == 0
    assert tokens[39:73] == [4-hand.count(t) for t in range(34)]
    others = [p for p in env.players if p.id != obs['player']]
    others[0].hand[0], others[1].hand[0] = others[1].hand[0], others[0].hand[0]
    env.wall.reverse()
    changed = player_observation(env, env.turn)
    changed['melds_all'] = [p['melds'] for p in changed['players']]
    assert _request(changed, rules, 1) == (line, actions)
    polluted = deepcopy(obs)
    polluted.update({'wall': [999], 'opponent_hands': [[666]], 'future_return': 12345})
    assert _request(polluted, rules, 1) == (line, actions)


def test_hidden_kong_identity_is_not_serialized_even_from_unmasked_input():
    rules, _, obs = state()
    other = (obs['player'] + 1) % 4
    obs['melds_all'][other] = [{'type': 'ANGANG', 'tiles': [0]*4}]
    first = _request(obs, rules, 1)
    obs['melds_all'][other][0]['tiles'] = [33]*4
    assert _request(obs, rules, 1) == first


def test_flower_replacement_and_gang_plus_one_contract():
    rules, _, obs = state(True)
    obs['n_remaining'] = 40
    for p in obs['players']:
        p['flowers'] = []
    obs['players'][0]['flowers'] = [34, 35, 36, 37]
    # Four unrevealed flowers in physical wall, 24 drawable slots => floor(24*.9)=21.
    assert int(_request(obs, rules, 1)[0].split()[3]) == 21
    rules.dead_wall_mode = 'gang_plus_one'
    obs['melds_all'][(obs['player']+1)%4] = [{'type': 'ANGANG', 'tiles': [None]*4}]
    assert int(_request(obs, rules, 1)[0].split()[3]) == 20


def test_own_chow_and_kong_encoding_and_blocked_discard_mask():
    rules, _, obs = state()
    obs['hand'] = [9, 10, 11, 12, 13, 14, 15, 16, 17, 27]
    obs['drawn'] = 28
    obs['melds'] = [{'type': 'CHI', 'tiles': [2, 0, 1]},
                    {'type': 'ANGANG', 'tiles': [33]*4}]
    obs['melds_all'][obs['player']] = deepcopy(obs['melds'])
    obs['legal_actions'] = [{'type': 'DISCARD', 'tile': 28, 'from': 'drawn'},
                            {'type': 'DISCARD', 'tile': 27, 'from': 'hand'}]
    tokens = list(map(int, _request(obs, rules, 1)[0].split()))
    assert tokens[38:43] == [2, 3, 0, 6, 33]
    _, candidates = _request(obs, rules, 1)
    assert candidates == list(reversed(obs['legal_actions']))
    assert all(a['tile'] not in (0, 1, 2) for a in candidates)


def test_all_chow_orientations_and_pong_kong_pass_mapping():
    rules, _, obs = state()
    obs.update(phase='REACTION', hand=list(range(16)), drawn=None,
               last_discard={'tile': 4, 'pid': (obs['player']+3)%4},
               legal_actions=[{'type': 'PONG'}, {'type': 'CHI', 'use': [2, 3]},
                              {'type': 'CHI', 'use': [3, 5]},
                              {'type': 'CHI', 'use': [5, 6]},
                              {'type': 'GANG'}, {'type': 'PASS'}])
    line, actions = _request(obs, rules, 1)
    assert list(map(int, line.split()))[-12:] == [1, -1, 4, 4, 5, 4, 6, 4, 7, 4, 8, 4]
    assert [a['type'] for a in actions] == ['PASS', 'CHI', 'CHI', 'CHI', 'PONG', 'GANG']


@pytest.mark.parametrize('reaction', [False, True])
def test_honor_chows_are_rejected_before_serialization(reaction):
    rules, _, obs = state()
    obs.update(hand=list(range(13)), drawn=13,
               melds=[{'type': 'CHI', 'tiles': [27, 28, 29]}])
    if reaction:
        obs.update(phase='REACTION', hand=list(range(16)), drawn=None, melds=[],
                   last_discard={'tile': 27},
                   legal_actions=[{'type': 'CHI', 'use': [28, 29]}, {'type': 'PASS'}])
    obs['melds_all'][obs['player']] = deepcopy(obs['melds'])
    with pytest.raises(ValueError, match='chow'):
        _request(obs, rules, 1)


def fake_bridge(tmp_path, body):
    if os.name != 'posix':
        pytest.skip('Bridge process requires POSIX pipes and executables')
    path = tmp_path/'fake'
    path.write_text(f'#!{sys.executable}\nimport sys,time\nprint("READY 1",flush=True)\n'+body)
    path.chmod(0o755)
    return path


def test_successive_requests_reuse_process_and_exact_host_action(tmp_path):
    rules, _, obs = state()
    path = fake_bridge(tmp_path,
                       'for line in sys.stdin:\n t=line.split();print("OK",t[1],0,flush=True)\n')
    with MeowCaTSStrategy(path, tmp_path, rules) as bot:
        pid = bot._process.pid
        assert bot.choose(obs) in obs['legal_actions']
        assert bot.choose(obs) in obs['legal_actions']
        assert bot.sequence == 2 and bot._process.pid == pid
        assert len(bot.latencies) == 2
        assert bot.choose({"legal_actions": [{"type": "HU"}]}) == {"type": "HU"}
        assert bot.choose({"legal_actions": [{"type": "PASS"}]}) == {"type": "PASS"}
        assert bot.sequence == 2
    assert bot._process.poll() is not None


@pytest.mark.parametrize('body,error', [
    ('for line in sys.stdin:\n print("OK 999 0",flush=True)\n', RuntimeError),
    ('for line in sys.stdin:\n print("OK 1 999",flush=True)\n', RuntimeError),
    ('for line in sys.stdin:\n print("garbage",flush=True)\n', RuntimeError),
    ('for line in sys.stdin:\n time.sleep(30)\n', TimeoutError),
    ('sys.exit(3)\n', RuntimeError),
])
def test_protocol_failures_reap_child_without_fallback(tmp_path, body, error):
    rules, _, obs = state()
    path = fake_bridge(tmp_path, body)
    bot = MeowCaTSStrategy(path, tmp_path, rules, timeout=2)
    bot.timeout = .1
    with pytest.raises(error):
        bot.choose(obs)
    assert bot._process.poll() is not None
    assert bot._stderr.closed


def test_malformed_visible_counts_fail_before_sending(tmp_path):
    rules, _, obs = state()
    obs['hand'] = [0]*16
    path = fake_bridge(tmp_path, 'for line in sys.stdin:\n print("OK 1 0",flush=True)\n')
    with MeowCaTSStrategy(path, tmp_path, rules) as bot:
        with pytest.raises(ValueError):
            bot.choose(obs)
        assert bot._process.poll() is not None


@pytest.mark.skipif(os.name != 'posix' or not os.environ.get('MEOWCATS_BRIDGE'),
                    reason='Requires POSIX and an isolated native bridge')
def test_real_cpp_turn_reaction_and_multiple_requests():
    binary = Path(os.environ['MEOWCATS_BRIDGE'])
    runtime = Path(os.environ['MEOWCATS_RUNTIME'])
    rules, _, obs = state()
    with MeowCaTSStrategy(binary, runtime, rules) as bot:
        assert bot.choose(obs) in obs['legal_actions']
        # Real 16-tile reaction: two 1W for a pong, two potential chow variants.
        obs.update(phase='REACTION', hand=[0,0,1,2,3,4,5,9,10,11,18,19,20,27,28,29],
                   drawn=None, last_discard={'tile': 0, 'pid': 1},
                   legal_actions=[{'type': 'PASS'}, {'type': 'PONG'},
                                  {'type': 'CHI', 'use': [1,2]}])
        assert bot.choose(obs) in obs['legal_actions']
        assert bot.sequence == 2


@pytest.mark.skipif(os.name != 'posix' or not os.environ.get('MEOWCATS_BRIDGE'),
                    reason='Requires POSIX and an isolated native bridge')
def test_real_cpp_no_honor_hand_and_restricted_discard_sources():
    rules, _, obs = state()
    obs['hand'] = [0,0,1,2,3,4,5,9,10,11,18,19,20,24,25,26]
    obs['drawn'] = 8
    obs['legal_actions'] = [{'type': 'DISCARD', 'tile': 8, 'from': 'drawn'},
                            {'type': 'DISCARD', 'tile': 0, 'from': 'hand'}]
    with MeowCaTSStrategy(os.environ['MEOWCATS_BRIDGE'],
                         os.environ['MEOWCATS_RUNTIME'], rules) as bot:
        assert bot.choose(obs) in obs['legal_actions']


@pytest.mark.skipif(os.name != 'posix' or not os.environ.get('MEOWCATS_BRIDGE'),
                    reason='Requires POSIX and an isolated native bridge')
@pytest.mark.parametrize('case', ['own-melds', 'angang', 'kakan', 'gang'])
def test_real_cpp_melds_and_kong_candidates(case):
    rules, _, obs = state()
    if case == 'own-melds':
        obs['hand'] = [9,10,11,12,13,14,15,16,17,27]
        obs['drawn'] = 28
        obs['melds'] = [{'type': 'CHI', 'tiles': [0,1,2]},
                        {'type': 'ANGANG', 'tiles': [33]*4}]
        obs['legal_actions'] = [{'type': 'DISCARD', 'tile': 27, 'from': 'hand'},
                                {'type': 'DISCARD', 'tile': 28, 'from': 'drawn'}]
    elif case == 'angang':
        obs['hand'] = [0,0,0,0,1,2,3,9,10,11,18,19,20,27,28,29]
        obs['drawn'] = 30
        obs['legal_actions'] = [{'type': 'ANGANG', 'tile': 0},
                                {'type': 'DISCARD', 'tile': 30, 'from': 'drawn'},
                                {'type': 'DISCARD', 'tile': 1, 'from': 'hand'}]
    elif case == 'kakan':
        obs['hand'] = [0,0,1,2,3,4,5,9,10,11,18,19,20]
        obs['drawn'] = 33
        obs['melds'] = [{'type': 'PONG', 'tiles': [33]*3}]
        obs['legal_actions'] = [{'type': 'KAKAN', 'tile': 33},
                                {'type': 'DISCARD', 'tile': 33, 'from': 'drawn'},
                                {'type': 'DISCARD', 'tile': 0, 'from': 'hand'}]
    else:
        obs['phase'] = 'REACTION'
        obs['hand'] = [0,0,0,1,2,3,9,10,11,18,19,20,24,25,26,27]
        obs['drawn'] = None
        obs['last_discard'] = {'tile': 0, 'pid': (obs['player']+3)%4}
        obs['rivers'][(obs['player']+3)%4] = [0]
        obs['legal_actions'] = [{'type': 'PASS'}, {'type': 'PONG'}, {'type': 'GANG'}]
    obs['melds_all'][obs['player']] = deepcopy(obs['melds'])
    with MeowCaTSStrategy(os.environ['MEOWCATS_BRIDGE'],
                         os.environ['MEOWCATS_RUNTIME'], rules) as bot:
        assert bot.choose(obs) in obs['legal_actions']
        assert bot.choose(obs) in obs['legal_actions']
