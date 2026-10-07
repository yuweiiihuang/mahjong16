"""Player visibility, provenance, completion and CLI dataset contracts."""
from copy import deepcopy
from contextlib import contextmanager
import json

import pytest

from app.hand_store import HandStore, stored_hand
from app import replay
from app.training_export import decision_samples, player_observation
from app.web import WebTable
from domain.gameplay.game_env import Mahjong16Env
from domain.gameplay.recording import HandRecorder
from domain.rules.ruleset import Ruleset
from tests.helpers.tile_pool import TilePool


def test_completed_web_samples_keep_decision_time_and_source(tmp_path):
    store = HandStore(tmp_path / 'hands.sqlite3')
    try:
        table = WebTable(7, human_pids={0, 1, 2, 3}, record_store=store)
        expected = []
        while not table.env.done:
            pid = table.actor()
            action = table.bot.choose(table.env._obs(pid))
            expected.append((pid, list(table.env.players[pid].hand), action))
            table.apply(action, pid=pid, source='human')
            table.advance()
        document = stored_hand(store.path, table.env.recorder.records[-1]['hand_id'])
    finally:
        store.close()
    samples = decision_samples(document)
    assert [(row['pid'], row['observation']['hand'], row['action'])
            for row in samples] == expected
    assert all(row['source'] == 'human' and row['player_id'] for row in samples)
    assert all(row['final_seat_payment'] == document['settlement']['payments'][row['pid']]
               for row in samples)
    assert all(not any(key in row for key in ('reward', 'next_obs', 'done', 'rewards'))
               for row in samples)
    assert any(row['source'] == 'auto_pass' for row in decision_samples(document, source='all'))
    assert decision_samples(document, source='bot') == []
    corrupt = deepcopy(document)
    corrupt['metadata']['decisions'][0]['pid'] = 3
    with pytest.raises(ValueError, match='來源'):
        decision_samples(corrupt)


def test_observation_is_invariant_to_other_players_private_state():
    env = Mahjong16Env(Ruleset(), seed=7)
    env.reset()
    env.players[1].melds = [{'type': 'ANGANG', 'tiles': [0] * 4, 'from_pid': None}]
    before = player_observation(env, 0)
    env.players[1].hand = [33] * len(env.players[1].hand)
    env.players[1].drawn = 32 if env.players[1].drawn is not None else None
    env.players[1].melds[0]['tiles'] = [33] * 4
    env.wall.reverse()
    env._public_live = [0] * 34  # Concealed kongs affect this aggregate: it is not public.
    env.reaction_responses = {1: {'type': 'HU'}}
    env.claims = [{'pid': 1, 'type': 'HU'}]
    assert player_observation(env, 0) == before
    assert before['players'][1]['melds'][0]['tiles'] == [None] * 4
    assert not any(key in before for key in (
        'wall', 'live_public', 'claims', 'reaction_responses', 'pending_reactions',
        'initial_state', 'final_hands', 'setup',
    ))
    assert all('hand' not in player and 'drawn' not in player for player in before['players'])


def _recorded_dealer(monkeypatch):
    pool = TilePool()
    hand = [0] * 3 + [1] * 3 + [2] * 3 + [3] * 3 + [4] * 3 + [8]
    pool.take(hand + [0])
    remaining = pool.remaining()
    hands = [hand] + [remaining[index:index + 16] for index in (0, 16, 32)]
    pool = TilePool()
    for tiles in hands:
        pool.take(tiles)
    pool.take([0])
    draws = [hands[pid][index] for index in range(16) for pid in range(4)] + [0]
    wall = pool.remaining() + list(reversed(draws))
    monkeypatch.setattr('domain.table.deal.full_wall', lambda *_: list(wall))
    recorder = HandRecorder()
    env = Mahjong16Env(Ruleset(include_flowers=False,
                              randomize_seating_and_dealer=False), recorder=recorder)
    env.reset()
    return env, recorder


def test_ting_action_uses_verified_legal_label_not_untrusted_waits(monkeypatch):
    env, recorder = _recorded_dealer(monkeypatch)
    expected = next(a for a in env.legal_actions(0)
                    if a['type'] == 'TING' and a['from'] == 'hand')
    submitted = {**expected, 'waits': {'cookie': 'SECRET', 'opponent_hand': 'SECRET'}}
    submitted.pop('from')  # The engine accepts this historical default.
    env.step(submitted, pid=0)
    rows = decision_samples(recorder.document(), source='all', include_incomplete=True)
    assert rows[0]['action'] == expected
    assert 'SECRET' not in json.dumps(rows)


def test_recorded_concealed_kong_is_visible_only_to_owner(monkeypatch):
    env, recorder = _recorded_dealer(monkeypatch)
    env.step({'type': 'ANGANG', 'tile': 0}, pid=0)
    action = next(a for a in env.legal_actions(0) if a['type'] == 'DISCARD')
    env.step(action, pid=0)
    env.step({'type': 'PASS'}, pid=1)
    document = recorder.document()
    assert decision_samples(document, source='all') == []  # Incomplete is opt-in.
    rows = decision_samples(document, source='all', include_incomplete=True)
    assert len(rows) == 3 and all(row['source'] == 'unknown' for row in rows)
    assert rows[1]['observation']['melds'][0]['tiles'] == [0] * 4
    assert rows[2]['pid'] == 1
    assert rows[2]['observation']['players'][0]['melds'][0]['tiles'] == [None] * 4
    assert all(row['final_seat_payment'] is None for row in rows)
    assert decision_samples(document, include_incomplete=True) == []
    document['steps'][0]['seq'] = 99
    with pytest.raises(ValueError):
        decision_samples(document, source='all', include_incomplete=True)


def test_dataset_cli_sqlite_and_invalid_input_leave_no_output(tmp_path, monkeypatch):
    store = HandStore(tmp_path / 'hands.sqlite3')
    try:
        table = WebTable(7, human_pids=set(), record_store=store)
        assert table.env.done
        target = tmp_path / 'decisions.jsonl'
        monkeypatch.setattr('sys.argv', ['replay', 'dataset', str(target),
                                        '--db', str(store.path), '--source', 'bot'])
        replay.main()
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        assert rows and all(row['source'] == 'bot' for row in rows)
        assert all(row['hand_status'] == 'completed' for row in rows)
        first = target.read_bytes()
        with pytest.raises(SystemExit):
            replay.main()
        assert target.read_bytes() == first
        document = stored_hand(store.path, table.env.recorder.records[-1]['hand_id'])
    finally:
        store.close()
    document['engine_version'] = 'incompatible'
    record = tmp_path / 'corrupt.json'
    record.write_text(json.dumps(document))
    target = tmp_path / 'rejected.jsonl'
    monkeypatch.setattr('sys.argv', ['replay', 'dataset', str(target),
                                    '--record', str(record), '--source', 'all'])
    with pytest.raises(SystemExit):
        replay.main()
    assert not target.exists()


def test_write_failure_never_publishes_a_partial_dataset(tmp_path, monkeypatch):
    env, recorder = _recorded_dealer(monkeypatch)
    env.step({'type': 'ANGANG', 'tile': 0}, pid=0)
    env.step(next(a for a in env.legal_actions(0) if a['type'] == 'DISCARD'), pid=0)
    record = tmp_path / 'hand.json'
    record.write_text(json.dumps(recorder.document()))
    target = tmp_path / 'dataset.jsonl'
    original = replay.open_private_record

    @contextmanager
    def failing_output(path):
        with original(path) as handle:
            class FailSecondWrite:
                count = 0

                def write(self, value):
                    self.count += 1
                    if self.count == 2:
                        raise OSError('simulated disk full')
                    return handle.write(value)

            yield FailSecondWrite()

    monkeypatch.setattr(replay, 'open_private_record', failing_output)
    monkeypatch.setattr('sys.argv', ['replay', 'dataset', str(target),
                                    '--record', str(record), '--source', 'all',
                                    '--include-incomplete'])
    with pytest.raises(SystemExit):
        replay.main()
    assert not target.exists()
    assert not list(tmp_path.glob('.dataset.jsonl.*.tmp'))
