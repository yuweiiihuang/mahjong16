"""Viewer-relative presentation shared by live rooms and completed-hand replay."""
from copy import deepcopy


def relative_snapshot(state: dict, viewer: int) -> dict:
    """Rotate a private snapshot in place; the caller already selected its viewer."""
    relative = lambda pid: None if pid is None else (pid - viewer) % 4
    order = [(viewer + i) % 4 for i in range(4)]
    for key in ('players', 'melds_all', 'rivers', 'seat_winds', 'totals'):
        state[key] = [state[key][pid] for pid in order]
    if 'final_hands' in state:
        state['final_hands'] = [state['final_hands'][pid] for pid in order]
    for key in ('player', 'actor', 'winner', 'dealer'):
        state[key] = relative(state[key])
    state['seating_order'] = [relative(pid) for pid in state['seating_order']]
    if state['last_discard']:
        state['last_discard']['pid'] = relative(state['last_discard']['pid'])
    for event in state['events']:
        event['pid'] = relative(event['pid'])
        if 'from_pid' in event:
            event['from_pid'] = relative(event['from_pid'])
    for melds in state['melds_all']:
        for meld in melds:
            if 'from_pid' in meld:
                meld['from_pid'] = relative(meld['from_pid'])
    for player in state.get('final_hands', []):
        for meld in player['melds']:
            if 'from_pid' in meld:
                meld['from_pid'] = relative(meld['from_pid'])
    state['melds'] = deepcopy(state['melds_all'][0])
    for pid, player in enumerate(state['players']):
        player['melds'] = deepcopy(state['melds_all'][pid])
    if state['settlement']:
        state['settlement'] = deepcopy(state['settlement'])
        result = state['settlement']
        result['payer'] = relative(result['payer'])
        result['payments'] = [result['payments'][pid] for pid in order]
    # Engine aggregate counts may include concealed kongs; never send them online.
    state.pop('live_public', None)
    return state
