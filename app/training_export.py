"""Offline decision facts, separated from future labels and hidden engine state."""
from __future__ import annotations

from copy import deepcopy

from domain.gameplay.game_env import MahjongEnvironment
from domain.gameplay.recording import _turn_action, replay_hand

SOURCES = ('human', 'bot', 'auto_pass', 'auto_ting', 'unknown')


def player_observation(env: MahjongEnvironment, pid: int) -> dict:
    """Whitelist decision-time information; mask other seats' concealed kong identities."""
    raw = env._obs(pid)
    observation = {key: deepcopy(raw[key]) for key in (
        'player', 'phase', 'hand', 'drawn', 'flowers', 'melds', 'declared_ting',
        'blocked_discards', 'rivers', 'n_remaining', 'last_discard',
    )}
    players = []
    for seat, player in enumerate(env.players):
        melds = deepcopy(player.melds)
        if seat != pid:
            for meld in melds:
                if meld['type'] == 'ANGANG':
                    meld['tiles'] = [None] * len(meld['tiles'])
        players.append({
            'count': len(player.hand) + int(player.drawn is not None),
            'has_drawn': player.drawn is not None, 'flowers': list(player.flowers),
            'melds': melds, 'declared_ting': player.declared_ting,
        })
    observation.update({
        'players': players, 'legal_actions': deepcopy(env.legal_actions(pid)),
        'dealer': env.dealer_pid, 'quan_feng': env.quan_feng,
        'seat_winds': list(env.seat_winds), 'dealer_streak': env.dealer_streak,
    })
    return observation


def decision_samples(document: dict, *, source: str = 'human',
                     include_incomplete: bool = False) -> list[dict]:
    """Verify a hand and rebuild actor observations; no RL reward or next_obs is inferred."""
    if source not in (*SOURCES, 'all'):
        raise ValueError('不支援的操作來源。')
    replay_hand(document)  # Reject a corrupt or incompatible record before emitting any rows.
    steps = document['steps']
    if not steps or (document['status'] != 'completed' and not include_incomplete):
        return []
    metadata = document.get('metadata', {})
    if not isinstance(metadata, dict):
        raise ValueError('牌譜 metadata 格式錯誤。')
    if metadata.get('table_id') is not None and not isinstance(metadata['table_id'], str):
        raise ValueError('牌譜桌 ID 格式錯誤。')
    contexts = metadata.get('decisions')
    if contexts is not None:
        if not isinstance(contexts, list) or len(contexts) != len(steps):
            raise ValueError('操作來源紀錄與牌譜步驟不一致。')
        for step, context in zip(steps, contexts):
            if (not isinstance(context, dict) or type(context.get('seq')) is not int
                    or type(context.get('pid')) is not int or context.get('seq') != step['seq']
                    or context.get('pid') != step['pid']
                    or context.get('source') not in SOURCES
                    or (context.get('player_id') is not None
                        and not isinstance(context['player_id'], str))):
                raise ValueError('操作來源紀錄與牌譜步驟不一致。')
    else:
        contexts = [{'source': 'unknown', 'player_id': None} for _ in steps]

    # Reuse the verified replay initializer without changing domain fingerprints or
    # duplicating wall/deal reconstruction. The empty prefix is a valid private record.
    env = replay_hand({**document, 'steps': [], 'status': 'incomplete',
                       'settlement': None, 'final_hash': steps[0]['before_hash']})
    samples = []
    for step, context in zip(steps, contexts):
        if source == 'all' or source == context['source']:
            pid = step['pid']
            observation = player_observation(env, pid)
            # The recorder accepts historical TURN defaults and ignores TING.waits.
            # Export the trusted legal candidate, never arbitrary submitted waits.
            action = next(candidate for candidate in observation['legal_actions']
                          if (_turn_action(candidate) == _turn_action(step['action'])
                              if env.phase == 'TURN' else candidate == step['action']))
            samples.append({
                'dataset_version': 1, 'hand_id': document['hand_id'],
                'engine_version': document['engine_version'],
                'hand_format_version': document['format_version'],
                'table_id': metadata.get('table_id'), 'seq': step['seq'], 'pid': pid,
                'source': context['source'], 'player_id': context.get('player_id'),
                'reaction_window': step['window'],
                'has_choice': len(observation['legal_actions']) > 1,
                'observation': observation, 'action': deepcopy(action),
                'hand_status': document['status'],
                'storage_status': document.get('storage_status', document['status']),
                # A seat's final payment is a future label, not this person's reward:
                # another person/bot may have controlled the seat during the hand.
                'final_seat_payment': (document['settlement']['payments'][pid]
                                       if document['settlement'] is not None else None),
            })
        env.step(deepcopy(step['action']), pid=step['pid'])
    return samples
