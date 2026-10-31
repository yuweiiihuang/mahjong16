"""Participant-only summaries and verified, read-only browser replay frames."""
from copy import deepcopy

from app.hand_store import HandStore
from app.ai_history import seat_ai_history
from app.web_view import relative_snapshot
from domain.gameplay.recording import engine_version, replay_hand
from domain.scoring.score_types import ScoringTable


def viewer_seat(document: dict, player_id: str, *, current: bool = False) -> int:
    """Authorize a participant using recorded IDs, never a submitted seat number."""
    metadata = document['metadata']
    players = metadata.get('recovery', {}).get('players', []) if current else metadata['players']
    matches = [pid for pid, player in enumerate(players) if player['player_id'] == player_id]
    if not current:
        matches.extend(event['pid'] for event in metadata.get('seat_events', [])
                       if event['player_id'] == player_id and 'pid' in event
                       and (document['status'] != 'completed'
                            or event['after_seq'] < len(document['steps'])))
    if not matches:
        raise ValueError('找不到你的牌局紀錄。')
    return matches[-1]


def can_resume(document: dict, store: HandStore, player_id: str) -> bool:
    """Reject obsolete table heads, expired tables and incompatible engine versions."""
    recovery = document['metadata'].get('recovery', {})
    reasons = (None, 'server_restart')
    if document['metadata']['source'] == 'practice':
        reasons += ('replaced_by_resume', 'session_expired')
    if (recovery.get('version') != 1 or document['engine_version'] != engine_version()
            or document.get('interruption_reason') not in reasons
            or store.latest_hand_id(document['metadata']['table_id']) != document['hand_id']):
        return False
    try:
        viewer_seat(document, player_id, current=True)
    except ValueError:
        return False
    return True


def _player_names(players: list[dict]) -> list[str]:
    """Use saved human names and the table's canonical names for bot seats."""
    return [player['name'] if player['human'] else name for player, name in
            zip(players, ['電腦玩家', '陳予安', '林小滿', '周子墨'])]


def session_summary(head: dict) -> dict:
    """Describe one durable session without disclosing any concealed game state."""
    names = _player_names(head['current_players'] or head['players'])
    return {
        'id': head['table_id'], 'hand_id': head['hand_id'], 'players': names,
        'source': head['source'], 'room_code': head['room_code'],
        'ai': seat_ai_history(head),
        'started_at': head['session_started'], 'round': head['round'],
        'completed_hands': head['completed_hands'],
        'established': head['completed_hands'] > 0,
        'done': head['status'] == 'completed',
        'totals': head['totals_after'] or head['totals_before'],
        'quan_feng': head['quan_feng'], 'dealer': head['dealer'],
        'seat_winds': head['seat_winds'],
        'resumable': head['current_participant'] and head['recovery_version'] == 1 and
                     head['engine_version'] == engine_version() and head['reason'] in
                     ((None, 'server_restart', 'replaced_by_resume', 'session_expired')
                      if head['source'] == 'practice' else (None, 'server_restart')),
    }


def session_statistics(store: HandStore, player_id: str, table_id: str) -> dict:
    """Aggregate every settled hand, including zero-payment draws, in one owned session."""
    hands = store.session_hands(player_id, table_id=table_id)
    if not hands:
        raise ValueError('找不到你的 Session。')
    seats = [{'wins': 0, 'tsumo': 0, 'ron': 0, 'deal_ins': 0, 'net': 0} for _ in range(4)]
    points = [{'round': 0, 'totals': hands[0]['totals_before'],
               'ai': seat_ai_history(hands[0])}]
    records = []
    draws = 0
    for hand in hands:
        result = hand['result']
        if hand['status'] != 'completed' or result is None:
            continue
        winner = result['winner']
        if winner is None:
            draws += 1
        else:
            seats[winner]['wins'] += 1
            seats[winner]['tsumo' if result['win_source'] == 'TSUMO' else 'ron'] += 1
            if hand['payer'] is not None:
                seats[hand['payer']]['deal_ins'] += 1
        for seat, payment in zip(seats, result['payments']):
            seat['net'] += payment
        usage = seat_ai_history(hand)
        points.append({'round': hand['round'], 'totals': hand['totals_after'], 'ai': usage})
        records.append({
            'id': hand['hand_id'], 'round': hand['round'], 'winner': winner,
            'win_source': result['win_source'], 'payments': result['payments'],
            'tai': result['tai'][winner] if winner is not None else None,
            'players': _player_names(hand['players']), 'ai': usage,
            'replayable': hand['participant'] and hand['engine_version'] == engine_version(),
        })
    count = len(records)
    for seat in seats:
        seat['average_payment'] = seat['net'] / count if count else 0
    return {**session_summary(hands[-1]), 'seats': seats, 'draws': draws,
            'points': points, 'hands': records}


def history(store: HandStore, player_id: str) -> list[dict]:
    """Return the last 100 participant records, excluding private state and credentials."""
    items = []
    for document in store.player_records(player_id):
        try:
            seat = viewer_seat(document, player_id)
        except ValueError:
            continue  # A post-settlement join grants a current seat, not past concealed hands.
        metadata = document['metadata']
        result = document['settlement']
        winner = result['winner'] if result else None
        defaults = ['玩家', '陳予安', '林小滿', '周子墨']
        names = [player['name'] if player['human'] else defaults[pid]
                 for pid, player in enumerate(metadata['players'])]
        for event in metadata.get('seat_events', []):
            if 'pid' in event:
                names[event['pid']] = event['name'] if event['human'] else defaults[event['pid']]
        items.append({
            'id': document['hand_id'], 'round': metadata['hand_index'],
            'started_at': metadata['started_at'], 'status': document['storage_status'],
            'source': metadata['source'], 'winner': names[winner] if winner is not None else None,
            'win_source': result['win_source'] if result else None,
            'tai': result['tai'][winner] if winner is not None else None,
            'payment': result['payments'][seat] if result else None,
            'replayable': document['status'] == 'completed' and
                          document['engine_version'] == engine_version(),
            'resumable': can_resume(document, store, player_id),
        })
    return items


def replay_frames(document: dict, player_id: str, viewer: int | None = None) -> list[dict]:
    """Verify a completed hand before exposing a participant-selected seat perspective."""
    from app.web import WebTable

    participant = viewer_seat(document, player_id)
    if document['status'] != 'completed':
        raise ValueError('未完成的牌局不能重播。')
    viewer = participant if viewer is None else viewer
    if type(viewer) is not int or viewer not in range(4):
        raise ValueError('重播視角必須是四個座位之一。')
    env = replay_hand(document)
    env.reset()
    table = WebTable(human_pids={0, 1, 2, 3}, defer_recording=True)
    table.env = env
    table.scoring = ScoringTable(**document['scoring'])
    table.totals = list(document['metadata']['totals_before'])
    table.round = document['metadata']['hand_index']
    table.record_players = deepcopy(document['metadata']['players'])
    table.ai_levels = list(document['metadata'].get('ai_levels', ['standard'] * 4))
    table.hand_manager_state = document['metadata'].get('recovery', {}).get('manager', {})
    table.settlement = None
    frames = []
    event = None

    def frame(seq: int) -> dict:
        for failure in document['metadata'].get('ai_failures', []):
            if failure['after_seq'] <= seq:
                table.ai_failures[failure['pid']] = failure['reason']
        if env.done:
            table.settle()
        state = relative_snapshot(table.snapshot(viewer), viewer)
        state['legal_actions'] = state['reaction_actions'] = []
        state['reaction_choice'] = None
        state['ting_options'] = state['ting_waits'] = []
        names = [player['name'] if player['human'] else name for player, name in zip(
            table.record_players, ['電腦玩家', '陳予安', '林小滿', '周子墨'])]
        state['replay_humans'] = [table.record_players[(viewer + i) % 4]['human']
                                  for i in range(4)]
        state['replay_viewer'] = viewer
        state['replay_seats'] = names
        state['replay_names'] = [names[(viewer + i) % 4] for i in range(4)]
        public_event = None
        if event:
            public_event = deepcopy(event)
            public_event['pid'] = (event['pid'] - viewer) % 4
            if event.get('from_pid') is not None:
                public_event['from_pid'] = (event['from_pid'] - viewer) % 4
            if event['type'] == 'ANGANG' and event['pid'] != viewer:
                public_event.pop('tile', None)
            public_event.pop('waits', None)
        return {'seq': seq, 'event': public_event, 'state': state}

    def seat_changes(seq: int) -> None:
        if env.done:
            return  # Later lobby changes must not rename the settled hand.
        for change in document['metadata'].get('seat_events', []):
            if change['after_seq'] == seq:
                table.record_players[change['pid']].update(
                    name=change['name'], human=change['human'])

    seat_changes(0)
    frames.append(frame(0))
    for step in document['steps']:
        accepted = []
        table.apply(step['action'], playback=accepted, pid=step['pid'])
        seat_changes(step['seq'])
        visible = accepted and accepted[-1]['type'] != 'PASS'
        if visible or env.done:
            event = deepcopy(table.events[-1]) if visible else {'type': 'DRAW_GAME'}
            if env.done:
                event = ({'type': 'HU', 'pid': env.winner, 'tile': env.win_tile}
                         if env.winner is not None else {'type': 'DRAW_GAME'})
                if env.win_source == 'RON':
                    event['from_pid'] = env.turn_at_win
            if 'pid' not in event:
                event['pid'] = step['pid']
            frames.append(frame(step['seq']))
        else:
            # Fold private reaction submissions and automatic draws into the same public event.
            frames[-1] = frame(step['seq'])
    return frames
