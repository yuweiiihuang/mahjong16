"""Seat policy, takeover, durable recovery and bounded native worker contracts."""
from concurrent.futures import Future
from copy import deepcopy
import os
from pathlib import Path
import sys
import threading

import pytest

from app.hand_store import HandStore, stored_hand
from app.web import WebTable
from app.web_ai import NativeSearches, Search
from app.web_rooms import RoomRegistry, WebRoom
from domain.gameplay.recording import private_state, replay_hand
from tests.web.test_record_api import call, server


class Decisions:
    """Controlled in-flight decisions; completion order belongs to each test."""

    def __init__(self):
        self.jobs = []

    def submit(self, observation, rules):
        future = Future()
        future.set_running_or_notify_cancel()
        search = Search(future, threading.Event())
        self.jobs.append((deepcopy(observation), search))
        return search


def room_with_search(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('app.web_rooms.time.monotonic', lambda: clock[0])
    service = Decisions()
    table = WebTable(7, human_pids={0, 1, 2, 3}, ai_service=service)
    room = WebRoom('1234ABCD', 'host', table)
    with room.changed:
        room.set_ai_levels('host', ['advanced'] * 4)
        room.start('host')
        # Host disconnects on the actual opening turn.
        clock[0] += 91
        room.tick(clock[0])
        clock[0] += 1
        room.tick(clock[0])
    assert len(service.jobs) == 1
    assert 'ai_pending' not in room.snapshot('host')
    return room, service, clock


def test_http_predeal_settings_owner_rotation_and_first_deal(tmp_path):
    # Explicit waiting fixture exercises the production HTTP predeal flow.
    with server(tmp_path / 'hands.sqlite3', waiting=True) as (address, handler, store):
        status, state, cookie = call(address, '/api/state')
        cookie = cookie.split(';')[0]
        assert status == 200 and state['waiting'] and state['ai_editable']
        assert state['hand'] == [] and state['legal_actions'] == [] and state['round'] == 0
        assert call(address, '/api/history', cookie)[1]['hands'] == []
        levels = ['advanced', 'standard', 'advanced', 'standard']
        assert call(address, '/api/ai', cookie, {'levels': levels})[0] == 200
        assert call(address, '/api/state', cookie)[1]['ai_levels'] == levels
        for invalid in (None, [], ['standard'] * 3, ['cheat'] * 4, [None] * 4):
            assert call(address, '/api/ai', cookie, {'levels': invalid})[0] == 400
        assert call(address, '/api/action', cookie, {'type': 'PASS'})[0] == 400
        status, state, _ = call(address, '/api/start', cookie, {})
        assert status == 200 and not state['waiting'] and state['round'] == 1
        assert state['hand'] and state['ai_levels'] == levels
        assert call(address, '/api/start', cookie, {})[0] == 400
        assert call(address, '/api/ai', cookie, {'levels': ['standard'] * 4})[0] == 200
        assert len(call(address, '/api/history', cookie)[1]['hands']) == 1
        _, room, _ = call(address, '/api/rooms', cookie, {})
        assert room['ai_levels'] == ['standard'] * 4
        assert call(address, '/api/ai', cookie, {'levels': levels})[0] == 200
        _, joined, guest = call(address, '/api/room/join', body={'code': room['room']['code']})
        guest = guest.split(';')[0]
        assert joined['ai_levels'] == levels[1:] + levels[:1]
        assert joined['seat_ids'] == [1, 2, 3, 0]
        assert not joined['ai_editable']
        assert call(address, '/api/ai', guest, {'levels': ['standard'] * 4})[0] == 400
        # Host handover also changes the relative-to-absolute write mapping.
        assert call(address, '/api/room/leave', cookie, {})[0] == 200
        guest_levels = ['advanced', 'advanced', 'standard', 'standard']
        assert call(address, '/api/ai', guest, {'levels': guest_levels})[1][
            'ai_levels'] == guest_levels
        shared = handler.rooms.get(guest.partition('=')[2])
        assert shared.table.ai_levels == ['standard', 'advanced', 'advanced', 'standard']
        call(address, '/api/room/start', guest, {})
        assert call(address, '/api/ai', guest, {'levels': guest_levels})[0] == 200


def test_durable_levels_fallback_actual_strategy_and_next_hand_recovery(tmp_path):
    store = HandStore(tmp_path / 'hands.sqlite3')
    try:
        table = WebTable(7, waiting=True, record_store=store)
        levels = ['standard', 'advanced', 'standard', 'advanced']
        table.set_ai_levels(levels)
        table.start_hand()
        while not table.env.done:
            table.act(table.bot.choose(table.env._obs(0)))
        record = stored_hand(store.path, table.env.recorder.records[-1]['hand_id'])
        replay_hand(record)
        bots = [decision for decision in record['metadata']['decisions']
                if decision['source'] == 'bot']
        assert {decision['strategy'] for decision in bots} == {'greedy'}
        assert any(d['pid'] == 1 and d['ai_failure'] == 'unavailable' for d in bots)
        assert {failure['pid'] for failure in record['metadata']['ai_failures']} == {1, 3}
        public = table.snapshot()
        assert public['ai_degraded'] == [False, True, False, True]
        assert 'ai_failures' not in public
        from app.web_records import replay_frames
        # Between-hand edits must never relabel the hand being replayed.
        record['metadata']['recovery']['ai_levels'] = ['standard'] * 4
        frames = replay_frames(record, table.record_players[0]['player_id'], viewer=1)
        assert all(frame['state']['ai_levels'] == levels[1:] + levels[:1]
                   for frame in frames)
        assert frames[-1]['state']['ai_degraded'] == [True, False, True, False]
        table.set_ai_levels(['advanced', 'standard', 'advanced', 'standard'])
        record = stored_hand(store.path, record['hand_id'])
        restored = WebTable.restore(record, store)
        assert restored.ai_levels == ['advanced', 'standard', 'advanced', 'standard']
        assert restored.ai_failures == table.ai_failures
        restored.human_pids = set(range(4))
        restored.next_hand()
        assert restored.ai_failures == [None] * 4
        assert restored.ai_levels == ['advanced', 'standard', 'advanced', 'standard']
        while not restored.env.done:
            pid = restored.actor()
            restored.apply(restored.bot.choose(restored.env._obs(pid)), pid=pid)
        restored.settle()
        restored.new_table(waiting=True)
        assert restored.ai_levels == ['standard'] * 4
    finally:
        store.close()


@pytest.mark.parametrize('change', ['reconnect', 'join', 'reaction', 'next', 'close'])
def test_stale_result_never_executes_after_control_or_decision_changes(monkeypatch, change):
    room, service, clock = room_with_search(monkeypatch)
    table = room.table
    observation, search = service.jobs[0]
    with room.changed:
        before = private_state(table.env)
        if change == 'reconnect':
            room.touch('host')
        elif change == 'join':
            # A free-seat decision is cancelled when that seat becomes human controlled.
            room.seats[0] = None
            room.join('replacement')
        elif change == 'reaction':
            # Another accepted decision invalidates a pending search, including private replies.
            table.apply(table.env.legal_actions(0)[0], pid=0)
        elif change == 'next':
            table.start_hand()
        else:
            table.interrupt_recording('room_expired')
        expected = private_state(table.env)
        search.future.set_result(observation['legal_actions'][-1])
        assert search.cancelled.is_set()
        assert table.ai_pending is None
        assert private_state(table.env) == expected
        if change in ('reconnect', 'join'):
            clock[0] += 1
            room.tick(clock[0])
            assert private_state(table.env) == before
            assert room.snapshot('host' if change == 'reconnect' else 'replacement')[
                'legal_actions']


def test_pending_search_does_not_block_another_room_and_uses_only_visible_snapshot(monkeypatch):
    room, service, clock = room_with_search(monkeypatch)
    observation = service.jobs[0][0]
    assert not {'wall', 'opponent_hands', 'live_public'} & observation.keys()
    assert all('hand' not in player for player in observation['players'])
    before = deepcopy(observation)
    room.table.env.players[1].hand.reverse()
    room.table.env.wall.reverse()
    assert observation == before
    # The actual registry loop calls room.tick serially under its registry lock.
    other = WebRoom('SECOND00', 'other', WebTable(12, human_pids=set(range(4))))
    with other.changed:
        other.start('other')
        clock[0] += 100
        other.tick(clock[0])
        clock[0] += 1
        other.tick(clock[0])
    assert other.table.events
    assert not service.jobs[0][1].future.done()
    with room.changed:
        room.table.interrupt_recording('test_cleanup')


@pytest.mark.parametrize('error', [TimeoutError('slow'), RuntimeError('native crash')])
def test_failed_search_downgrades_only_its_seat_for_this_hand(monkeypatch, error):
    room, service, clock = room_with_search(monkeypatch)
    with room.changed:
        service.jobs[0][1].future.set_exception(error)
        room.tick(clock[0])
        assert room.table.events
        assert room.table.ai_failures == [type(error).__name__, None, None, None]
        assert room.snapshot('host')['ai_degraded'] == [True, False, False, False]
        room.table.start_hand()
        assert room.table.ai_failures == [None] * 4
        room.table.interrupt_recording('test_cleanup')


def runtime_config(path):
    (path / 'config.ini').write_text('''[MCTS]
TotalSampleCount=2000
ThreadNum=0
WaitReleaseTree=1
UseTime=0
[BaseConfig]
SampleCount=2000
SampleFirstRound=100
SamplePerRound=100
UseTime=0
[Multithread]
ThreadNum=0
''')


@pytest.mark.parametrize('hang', ['initialize', 'choose', 'error'])
def test_real_adapter_timeout_or_crash_reaps_process_and_falls_back(tmp_path, monkeypatch, hang):
    import subprocess
    processes = []
    popen = subprocess.Popen

    def track(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr('bots.meowcats.subprocess.Popen', track)
    runtime_config(tmp_path)
    bridge = tmp_path / 'bridge'
    bridge.write_text(f'#!{sys.executable}\nimport os,sys,time\n'
                      'open(str(os.getpid())+".pid","w").write(str(os.getpid()))\n' +
                      ('time.sleep(10)\n' if hang == 'initialize' else
                       'print("READY 1",flush=True)\nfor line in sys.stdin:\n ' +
                       ('time.sleep(10)\n' if hang == 'choose' else 'sys.exit(4)\n')))
    bridge.chmod(0o755)
    service = NativeSearches(bridge, tmp_path, timeout=.5)
    try:
        table = WebTable(7, human_pids=set(range(4)), ai_service=service)
        table.ai_levels[0] = 'advanced'
        assert table.choose_bot(0) is None
        search = table.ai_pending[2]
        with pytest.raises((TimeoutError, RuntimeError)):
            search.future.result(timeout=3)
        action = table.choose_bot(0)
        assert action in table.env.legal_actions(0)
        assert table.ai_failures[0] in ('TimeoutError', 'RuntimeError')
    finally:
        service.close()
    assert processes
    assert all(process.poll() is not None for process in processes)


def test_worker_capacity_queue_cancellation_and_shutdown(tmp_path):
    runtime_config(tmp_path)
    bridge = tmp_path / 'bridge'
    bridge.write_text(f'#!{sys.executable}\nimport sys,time\ntime.sleep(10)\n')
    bridge.chmod(0o755)
    service = NativeSearches(bridge, tmp_path, timeout=.3)
    table = WebTable(7, human_pids=set(range(4)))
    from app.training_export import player_observation
    observation = player_observation(table.env, 0)
    observation['melds_all'] = [p['melds'] for p in observation['players']]
    try:
        searches = [service.submit(observation, table.env.rules) for _ in range(4)]
        assert all(search is not None for search in searches)
        assert service.submit(observation, table.env.rules) is None
        searches[-1].cancel()
        assert searches[-1].cancelled.is_set()
        assert not searches[-1].future.done()
        # Repeated cancellation cannot free capacity while workers remain occupied.
        for _ in range(100):
            searches[-1].cancel()
            assert service.submit(observation, table.env.rules) is None
    finally:
        service.close()
    assert all(search.future.done() for search in searches)
    assert not service.searches
    assert service.submit(observation, table.env.rules) is None


@pytest.mark.skipif(not os.environ.get('MEOWCATS_BRIDGE'), reason='Native bridge not configured')
@pytest.mark.parametrize('levels', [
    ['standard', 'advanced', 'standard', 'advanced'],
    ['standard', 'advanced', 'advanced', 'advanced'],
])
def test_native_mixed_and_three_advanced_seats_complete_recorded_hand(tmp_path, levels):
    service = NativeSearches(Path(os.environ['MEOWCATS_BRIDGE']),
                            Path(os.environ['MEOWCATS_RUNTIME']))
    store = HandStore(tmp_path / 'hands.sqlite3')
    try:
        table = WebTable(7, waiting=True, ai_service=service, record_store=store)
        table.set_ai_levels(levels)
        table.start_hand()
        for _ in range(1500):
            if table.env.done:
                break
            table.advance()
            if table.ai_pending:
                table.ai_pending[2].future.result(timeout=17)
            elif not table.env.done:
                table.act(table.bot.choose(table.env._obs(0)))
        assert table.env.done
        assert table.ai_failures == [None] * 4
        record = stored_hand(store.path, table.env.recorder.records[-1]['hand_id'])
        replay_hand(record)
        actual = {pid: {d['strategy'] for d in record['metadata']['decisions']
                        if d['pid'] == pid and d['source'] == 'bot'} for pid in range(1, 4)}
        assert actual == {pid: {'meowcats_2000' if levels[pid] == 'advanced' else 'greedy'}
                          for pid in range(1, 4)}
    finally:
        service.close()
        store.close()
    assert not service.searches


def test_real_pending_reaction_is_cancelled_by_private_reply_without_progress_leak(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('app.web_rooms.time.monotonic', lambda: clock[0])
    service = Decisions()
    table = WebTable(7, human_pids=set(range(4)), ai_service=service)
    room = WebRoom('1234ABCD', 'host', table)
    with room.changed:
        room.join('guest')
        room.start('host')
        # A deterministic reaction fixture, using the same engine transition as real play.
        env = table.env
        env.recorder = None
        env.phase = 'REACTION'
        env.reaction_queue = [1, 2, 3]
        env.reaction_idx = 0
        env.last_discard = {'pid': 0, 'tile': 1}
        env.players[0].river = [1]
        for pid in (1, 2, 3):
            env.players[pid].hand = [1, 1]
            env.players[pid].drawn = None
        table.ai_levels[2] = 'advanced'
        room.ready_at = 0
        room.tick(clock[0])
        assert table.ai_pending[1] == 2
        search = service.jobs[0][1]
        version = room.version
        assert 'ai_pending' not in room.snapshot('host')
        # Guest's PASS remains private, leaving the same discard unresolved.
        room.act('guest', version, 'private-pass', {'type': 'PASS'})
        assert env.phase == 'REACTION' and room.version == version
        assert search.cancelled.is_set()
        assert 'ai_pending' not in room.snapshot('host')
        before = private_state(env)
        search.future.set_result({'type': 'PONG'})
        room.tick(clock[0])
        assert private_state(env) == before
        assert len(service.jobs) == 2  # Only the new decision may subsequently be applied.
        table.interrupt_recording('test_cleanup')


def test_registry_join_cancels_free_seat_native_decision_without_changing_tiles(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('app.web_rooms.time.monotonic', lambda: clock[0])
    service = Decisions()
    registry = RoomRegistry()
    room = registry.create('host', lambda **kwargs: WebTable(7, ai_service=service, **kwargs))
    with room.changed:
        room.set_ai_levels('host', ['standard', 'advanced', 'standard', 'standard'])
        room.start('host')
        # Drive the normal host decision and forced replies to seat one's turn.
        for _ in range(100):
            room.ready_at = 0
            if room.table.actor() == 1 and room.table.env.phase == 'TURN':
                break
            pid = room.table.actor()
            room.apply(room.table.bot.choose(room.table.env._obs(pid)), pid=pid)
        assert room.table.actor() == 1 and room.table.env.phase == 'TURN'
        room.ready_at = 0
        room.tick(clock[0])
        clock[0] += 1
        room.tick(clock[0])
        search = room.table.ai_pending[2]
        before = private_state(room.table.env)
    registry.join('guest', room.code)
    with room.changed:
        assert room.seats[1] == 'guest'
        assert room.table.ai_levels[1] == 'advanced'
        search.future.set_result(service.jobs[0][0]['legal_actions'][0])
        room.tick(clock[0] + 1)
        assert search.cancelled.is_set()
        assert private_state(room.table.env) == before
        assert room.snapshot('guest')['legal_actions']


def test_practice_get_and_resume_serialize_old_table_results(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    with server(tmp_path / 'hands.sqlite3') as (address, handler, store):
        _, initial, cookie = call(address, '/api/state')
        cookie = cookie.split(';')[0]
        sid = cookie.partition('=')[2]
        table = handler.sessions[sid]
        while not table.env.done:
            table.act(table.bot.choose(table.env._obs(0)))
        first_hand = table.env.recorder.records[-1]['hand_id']
        call(address, '/api/new', cookie, {})
        call(address, '/api/start', cookie, {})
        old = handler.sessions[sid]
        service = Decisions()
        old.ai_service = service
        old.ai_levels[1:] = ['advanced'] * 3
        old.act(old.bot.choose(old.env._obs(0)))
        assert old.ai_pending
        service.jobs[0][1].future.set_result(service.jobs[0][0]['legal_actions'][0])
        captured = threading.Event()
        release = threading.Event()
        resuming = threading.Event()
        original_table = handler.table
        original_post = handler.do_POST

        def capture(request):
            result = original_table(request)
            captured.set()
            assert release.wait(5)
            return result

        def post(request):
            resuming.set()
            original_post(request)

        monkeypatch.setattr(handler, 'table', capture)
        monkeypatch.setattr(handler, 'do_POST', post)
        with ThreadPoolExecutor(max_workers=2) as pool:
            get = pool.submit(call, address, '/api/state', cookie)
            try:
                assert captured.wait(5)
                resume = pool.submit(call, address, '/api/resume', cookie,
                                     {'hand_id': first_hand})
                assert resuming.wait(5)
                acquired = handler.session_lock.acquire(blocking=False)
                if acquired:
                    handler.session_lock.release()
                assert not acquired, 'An old-table GET must serialize with Session replacement'
            finally:
                release.set()
            assert get.result(timeout=5)[0] == 200
            status, state, _ = resume.result(timeout=5)
            assert status == 200 and state['session_id'] == initial['session_id']
        assert old.ai_pending is None
        after = deepcopy(old.env.recorder.document())
        call(address, '/api/state', cookie)
        assert old.env.recorder.document() == after


def test_mid_hand_ai_preferences_wait_until_next_deal_and_survive_restore(tmp_path):
    store = HandStore(tmp_path / 'hands.sqlite3')
    try:
        table = WebTable(7, waiting=True, record_store=store)
        table.start_hand()
        original = ['standard'] * 4
        upcoming = ['standard', 'advanced', 'standard', 'standard']
        table.set_ai_levels(upcoming)
        table.set_ai_levels(original)
        assert table.next_ai_levels is None
        table.set_ai_levels(upcoming)
        assert table.ai_levels == original
        assert table.snapshot()['ai_levels'] == upcoming
        assert table.snapshot()['ai_hand_levels'] == original
        assert table.snapshot()['ai_editable']
        saved = stored_hand(store.path, table.env.recorder.records[-1]['hand_id'])
        restored = WebTable.restore(saved, store)
        assert restored.ai_levels == original and restored.next_ai_levels == upcoming
        while not restored.env.done:
            restored.act(restored.bot.choose(restored.env._obs(0)))
        completed = stored_hand(store.path, saved['hand_id'])
        assert completed['metadata']['ai_levels'] == original
        assert all(d['strategy'] == 'greedy' for d in completed['metadata']['decisions']
                   if d['source'] == 'bot')
        restored.next_hand()
        assert restored.ai_levels == upcoming and restored.next_ai_levels is None
        assert restored.env.recorder.metadata['ai_levels'] == upcoming
    finally:
        store.close()
