"""Local browser table backed by the existing Taiwan Mahjong rules engine."""
from __future__ import annotations

import argparse
import base64
import hmac
from copy import deepcopy
from dataclasses import asdict
import json
import secrets
import sqlite3
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from app.web_rooms import RoomRegistry, player_name
from app.hand_store import HandStore, PersistentHandRecorder, RecordingError, _now

from domain.gameplay.game_env import Mahjong16Env
from domain.gameplay.recording import replay_hand
from domain.rules.ruleset import Ruleset
from bots.greedy import GreedyBotStrategy
from app.table import TableManager, TableState
from domain.analysis import visible_count_global
from domain.rules.hands import waits_for_hand_16
from domain.scoring.engine import compute_payments, score_with_breakdown
from domain.scoring.lookup import load_scoring_assets
from domain.scoring.score_types import ScoringContext, ScoringTable

WEB_ROOT = Path(__file__).resolve().parents[1] / 'ui' / 'web'


class WebTable:
    """Engine-backed table with private viewer snapshots and legal human actions."""

    def __init__(self, seed: int | None = None, human_pids: set[int] | None = None, *,
                 record_store: HandStore | None = None, defer_recording: bool = False,
                 player_id: str | None = None):
        self.human_pids = {0} if human_pids is None else set(human_pids)
        self.auto_ting_discard = [True] * 4
        self.record_store = record_store
        self.recording_enabled = record_store is not None and not defer_recording
        self.recording_error = False
        self.table_id = str(uuid4())
        self.record_players = [
            {'player_id': str(uuid4()) if pid in self.human_pids else None,
             'name': '玩家' if pid in self.human_pids else '電腦玩家',
             'human': pid in self.human_pids} for pid in range(4)
        ]
        if player_id and 0 in self.human_pids:
            self.record_players[0]['player_id'] = player_id
        self.record_source = 'practice'
        self.env = Mahjong16Env(Ruleset(randomize_seating_and_dealer=False), seed=seed)
        self.bot = GreedyBotStrategy()
        self.events: list[dict] = []
        self.room_checkpoint = None
        self.request_id = None
        self.lock = threading.Lock()
        self.scoring = load_scoring_assets(
            self.env.rules.scoring_profile, self.env.rules.scoring_overrides_path
        )
        self.new_table()

    def new_table(self, *, activate_recording: bool = False) -> None:
        """Start a fresh practice table with fixed initial seats and 1,000 points each."""
        self.check_recording()
        if self.recording_enabled and getattr(self, 'round', 0) and not self.env.done:
            raise ValueError('本局尚未結束，請先胡牌或流局後再開新 Session。')
        self.table_id = str(uuid4())
        if activate_recording:
            self.recording_enabled = self.record_store is not None
        self.manager = TableManager(self.env.rules, seed=self.env.reset_rng_seed)
        self.manager.state = TableState(
            seat_winds=['E', 'S', 'W', 'N'], seating_order=[0, 1, 2, 3]
        )
        self.totals = [1000] * self.env.rules.n_players
        self.round = 0
        self.start_hand()

    def start_hand(self, playback: list | None = None) -> None:
        """Deal the next hand using the shared dealer and round-wind manager."""
        self.check_recording()
        self.round += 1
        self.events = []
        self.settlement = None
        self.hand_manager_state = asdict(self.manager.state)
        self.hand_manager_rng = self.manager.rng.getstate()
        if self.recording_enabled:
            metadata = {
                'table_id': self.table_id, 'hand_index': self.round,
                'started_at': _now(), 'source': self.record_source,
                'totals_before': list(self.totals),
                'players': deepcopy(self.record_players), 'seat_events': [], 'decisions': [],
            }
            self.env.recorder = PersistentHandRecorder(
                self.record_store, metadata, recovery=self.recovery_state)
        try:
            self.manager.start_hand(self.env)
        except RecordingError:
            self.recording_error = True
            raise
        self.advance(playback)

    def recovery_state(self) -> dict:
        """Save the table contract with each committed engine prefix, without credentials."""
        recovery = {
            'version': 1, 'manager': deepcopy(self.hand_manager_state),
            'manager_rng': self.hand_manager_rng, 'env_rng': self.env.rng.getstate(),
            'human_pids': sorted(self.human_pids),
            'auto_ting_discard': list(self.auto_ting_discard),
            'players': deepcopy(self.record_players),
        }
        if self.room_checkpoint is not None:
            recovery['room'] = self.room_checkpoint()
        return recovery

    @classmethod
    def restore(cls, document: dict, store: HandStore) -> WebTable:
        """Verify a durable prefix before restoring it; never reapply settled payments."""
        metadata = deepcopy(document['metadata'])
        recovery = metadata.get('recovery', {})
        if recovery.get('version') != 1:
            raise ValueError('這份舊牌譜不含續局資訊，只能查看紀錄。')
        env = replay_hand(document)
        # Replay uses a fixed-wall subclass; resumed future hands must shuffle normally.
        env.__class__ = Mahjong16Env
        env.reset_rng_seed = document['seed']
        table = cls(human_pids=set(recovery['human_pids']), defer_recording=True)
        table.env = env
        table.scoring = ScoringTable(**document['scoring'])
        table.manager = TableManager(env.rules)
        table.manager.state = TableState(**recovery['manager'])
        table.hand_manager_state = recovery['manager']
        table.hand_manager_rng = recovery['manager_rng']

        def tuples(value):
            return tuple(tuples(item) for item in value) if isinstance(value, list) else value

        env.rng.setstate(tuples(recovery['env_rng']))
        table.manager.rng.setstate(tuples(recovery['manager_rng']))
        table.record_store = store
        table.recording_enabled = True
        table.record_players = recovery['players']
        table.record_source = metadata['source']
        table.table_id = metadata['table_id']
        table.round = metadata['hand_index']
        table.auto_ting_discard = recovery['auto_ting_discard']
        table.totals = list(metadata['totals_before'])
        table.settlement = None
        if env.done:
            settlement = metadata.get('settlement')
            expected = [a + b for a, b in zip(table.totals, document['settlement']['payments'])]
            if (not settlement or metadata.get('totals_after') != expected or
                    settlement['payments'] != document['settlement']['payments']):
                raise ValueError('牌桌結算紀錄不一致，無法續局。')
            table.totals = expected
            table.settlement = settlement
            table.manager.finish_hand(env)
        recorder = PersistentHandRecorder(store, metadata, recovery=table.recovery_state)
        recorder.records = [{key: deepcopy(value) for key, value in document.items()
                             if key not in ('metadata', 'storage_status', 'interruption_reason')}]
        recorder._table = table.scoring
        # Window numbers are monotonically assigned when a turn opens reactions.
        windows = [step['window'] for step in document['steps'] if step['window'] is not None]
        recorder._window = max(windows, default=0)
        if env.phase == 'REACTION' and (not document['steps'] or
                                       document['steps'][-1]['phase'] != 'REACTION'):
            recorder._window += 1
        env.recorder = recorder
        return table

    def check_recording(self) -> None:
        """Keep failed tables stopped, without blocking other rooms or hiding the error."""
        if self.recording_error:
            raise RecordingError('牌譜保存失敗，本桌已暫停；請聯絡管理者。')

    def interrupt_recording(self, reason: str) -> None:
        """Retain a durable prefix when a table is discarded or replaced."""
        recorder = self.env.recorder
        if isinstance(recorder, PersistentHandRecorder) and recorder.records:
            try:
                self.record_store.interrupt(recorder.records[-1]['hand_id'], reason)
            except (OSError, sqlite3.Error) as error:
                self.recording_error = True
                raise RecordingError('牌譜保存失敗，本桌已暫停；請聯絡管理者。') from error

    def record_seat(self, pid: int, player: dict) -> None:
        """Record pseudonymous seat ownership changes without storing session credentials."""
        if self.record_players[pid] == player:
            return
        self.record_players[pid] = deepcopy(player)
        recorder = self.env.recorder
        if isinstance(recorder, PersistentHandRecorder):
            recorder.metadata['seat_events'].append({
                'after_seq': len(recorder.records[-1]['steps']),
                'at': _now(), 'pid': pid, **deepcopy(player),
            })
            try:
                recorder.persist()
            except RecordingError:
                self.recording_error = True
                raise

    def next_hand(self) -> dict:
        """Continue a completed hand without clearing accumulated points."""
        if not self.env.done:
            raise ValueError('本局尚未結束。')
        playback = []
        self.start_hand(playback)
        return {**self.snapshot(), 'playback': playback}

    def settle(self) -> None:
        """Settle a finished hand exactly once, before advancing dealer state."""
        if not self.env.done or self.settlement is not None:
            return
        ctx = ScoringContext.from_env(self.env, self.scoring)
        rewards, breakdown = score_with_breakdown(ctx)
        payments, _ = compute_payments(
            ctx, self.env.rules.base_points, self.env.rules.tai_points,
            rewards=rewards, breakdown=breakdown,
        )
        self.totals = [total + delta for total, delta in zip(self.totals, payments)]
        self.settlement = {
            'tai': rewards[self.env.winner] if self.env.winner is not None else 0,
            'breakdown': breakdown.get(self.env.winner, []),
            'payments': payments, 'base_points': self.env.rules.base_points,
            'tai_points': self.env.rules.tai_points,
            'payer': self.env.turn_at_win if self.env.win_source == 'RON' else None,
            'flower_win_type': self.env.flower_win_type,
        }
        if isinstance(self.env.recorder, PersistentHandRecorder):
            self.env.recorder.metadata.update({
                'totals_after': list(self.totals), 'settlement': deepcopy(self.settlement),
            })
            try:
                self.env.recorder.persist()
            except RecordingError:
                self.recording_error = True
                raise
        self.manager.finish_hand(self.env)

    def actor(self) -> int:
        """Return the turn actor or first unanswered seat for sequential clients."""
        if self.env.phase == 'REACTION':
            return self.env.reaction_queue[self.env.reaction_idx]
        return self.env.turn

    def apply(
        self, action: dict, playback: list | None = None, pid: int | None = None,
        *, source: str = 'human',
    ) -> None:
        """Apply and record an already validated action."""
        self.check_recording()
        pid, phase = self.actor() if pid is None else pid, self.env.phase
        if isinstance(self.env.recorder, PersistentHandRecorder):
            self.env.recorder.step_context = {
                'pid': pid, 'source': source,
                'player_id': self.record_players[pid]['player_id'],
            }
            if self.request_id is not None:
                self.env.recorder.step_context['request_id'] = self.request_id
        try:
            _, _, _, info = self.env.step(action, pid=pid)
        except RecordingError:
            self.recording_error = True
            raise
        resolved = info.get('resolved_claim')
        # Tentative or rejected claims can contain tiles still hidden in a player's hand.
        if resolved:
            self.events.append(deepcopy(resolved))
        elif phase == 'TURN':
            self.events.append({'pid': pid, **deepcopy(action)})
        self.events = self.events[-60:]
        if resolved:
            self.record_frame(playback, resolved['pid'], resolved['type'])
        elif phase == 'TURN':
            self.record_frame(playback, pid, action['type'])

    def record_frame(self, playback: list | None, pid: int, action_type: str) -> None:
        """Capture immutable public states for presentation, without further gameplay."""
        if playback is not None:
            state = deepcopy(self.snapshot())
            state['legal_actions'] = []
            state['ting_options'] = []
            playback.append({'state': state, 'pid': pid, 'type': action_type})

    def ting_discard(self) -> dict | None:
        """Return the forced drawn discard after ting, retaining any winning choice."""
        if self.env.done or self.env.phase != 'TURN':
            return None
        pid = self.actor()
        if not self.auto_ting_discard[pid]:
            return None
        actions = self.env.legal_actions(pid)
        if (self.env.players[pid].declared_ting and len(actions) == 1
                and actions[0]['type'] == 'DISCARD' and actions[0]['from'] == 'drawn'):
            return actions[0]
        return None

    def advance(
        self, playback: list | None = None, *, auto_discard_ting: bool = True
    ) -> None:
        """Play bots until a meaningful human choice or round end."""
        while not self.env.done:
            if self.env.phase == 'REACTION':
                # Bots and forced passes must not wait behind a human's decision.
                automatic = next((pid for pid in self.env.pending_reactions()
                                  if pid not in self.human_pids
                                  or self.env.legal_actions(pid) == [{'type': 'PASS'}]), None)
                if automatic is None:
                    return
                action = self.bot.choose(self.env._obs(automatic))
                self.apply(action, playback, pid=automatic,
                           source=('auto_pass' if self.env.legal_actions(automatic)
                                   == [{'type': 'PASS'}] else 'bot'))
                continue
            pid = self.actor()
            actions = self.env.legal_actions(pid)
            ting_discard = self.ting_discard() if auto_discard_ting else None
            if ting_discard is not None:
                self.apply(ting_discard, playback, source='auto_ting')
                continue
            if pid in self.human_pids:
                if actions == [{'type': 'PASS'}]:
                    self.apply(actions[0], playback, source='auto_pass')
                    continue
                return
            action = self.bot.choose(self.env._obs(pid))
            if self.env.phase == 'TURN':
                self.record_frame(playback, pid, 'THINK')
            self.apply(action, playback, source='bot')
        if playback is not None and (not playback or not playback[-1]['state']['done']):
            self.record_frame(playback, self.env.winner or 0,
                              'HU' if self.env.winner is not None else 'DRAW_GAME')
        self.settle()

    def act(self, action: dict) -> dict:
        """Reject stale/forged moves before mutating game state."""
        if (self.env.done or (self.env.phase != 'REACTION' and self.actor() != 0)
                or action not in self.env.legal_actions(0)):
            raise ValueError('這個操作已失效，請重新選牌。')
        playback = []
        self.apply(action, playback, pid=0)
        self.advance(playback)
        return {**self.snapshot(), 'playback': playback}

    def snapshot(self, viewer: int = 0) -> dict:
        """Expose public table state and the selected player's own hand."""
        self.check_recording()
        env = self.env
        result = deepcopy(env._obs(viewer))
        result.update({
            'auto_ting_discard': self.auto_ting_discard[viewer],
            'player_name': self.record_players[viewer]['name'],
            'legal_actions': (env.legal_actions(viewer)
                              if not env.done and (env.phase == 'REACTION'
                                                   or self.actor() == viewer) else []),
            'reaction_choice': (deepcopy(env.reaction_responses.get(viewer))
                                if env.phase == 'REACTION' else None),
            'reaction_actions': (env._reaction_phase_actions(viewer, include_submitted=True)
                                 if env.phase == 'REACTION' else []),
            # Reaction eligibility is private; only normal turn actors are public.
            'actor': None if env.done or env.phase == 'REACTION' else self.actor(),
            'done': env.done,
            'winner': env.winner, 'win_source': env.win_source,
            'dealer': env.dealer_pid, 'events': deepcopy(self.events),
            'round': self.round, 'quan_feng': env.quan_feng,
            # Use the hand's starting manager state; settlement already advances the next hand.
            'jang_count': self.hand_manager_state.get('jang_count'),
            'seat_winds': list(env.seat_winds), 'seating_order': list(env.seating_order),
            'dealer_streak': env.dealer_streak, 'totals': list(self.totals),
            'settlement': self.settlement,
            'remaining': max(0, len(env.wall) - env._dead_wall_reserved()),
            'players': [{'count': len(p.hand) + int(p.drawn is not None),
                         'has_drawn': p.drawn is not None,
                         'flowers': list(p.flowers), 'melds': deepcopy(p.melds),
                         'ting': p.declared_ting} for p in env.players],
        })
        if self.record_source == 'practice' and self.recording_enabled:
            result['session_id'] = self.table_id
        # Playback must not reveal opponents' concealed kongs or declared waits.
        for event in result['events']:
            if event['pid'] != viewer:
                event.pop('waits', None)
                if event['type'] == 'ANGANG':
                    event.pop('tile', None)
        for pid, player in enumerate(result['players']):
            if pid == viewer:
                continue
            melds = deepcopy(player['melds'])
            for meld in melds:
                if meld['type'] == 'ANGANG':
                    meld['tiles'] = [None] * len(meld['tiles'])
            player['melds'] = result['melds_all'][pid] = melds
        # Unseen counts use only the human hand and public tiles, never the wall or bots.
        visible = {**result, 'melds_all': [
            [meld for meld in melds if pid == viewer or meld['type'] != 'ANGANG']
            for pid, melds in enumerate(result['melds_all'])
        ]}

        def wait_details(waits: list[int]) -> list[dict]:
            return [{'tile': tile, 'unseen': max(
                0, 4 - visible_count_global(tile, visible) - int(result['drawn'] == tile)
            )} for tile in waits]

        result['ting_options'] = [
            {'tile': a['tile'], 'from': a['from'], 'waits': wait_details(a['waits'])}
            for a in result['legal_actions'] if a['type'] == 'TING'
        ]
        result['ting_waits'] = wait_details(waits_for_hand_16(
            result['hand'], result['melds'], env.rules
        )) if not env.done and (result['declared_ting'] or result['drawn'] is None) else []
        if env.done:
            # Reveal complete player perspectives only after the hand has finished.
            result['final_hands'] = [
                {'hand': list(player.hand), 'drawn': player.drawn,
                 'melds': deepcopy(player.melds), 'flowers': list(player.flowers)}
                for pid, player in enumerate(env.players)
            ]
            result['win_tile'] = env.win_tile
        if env.done and env.winner is not None:
            winner = env.players[env.winner]
            if env.flower_win_type:
                result['winning_hand'] = sorted(winner.flowers)
                if env.win_tile is not None and env.win_tile not in winner.flowers:
                    result['winning_hand'].append(env.win_tile)
            else:
                result['winning_hand'] = sorted(winner.hand) + (
                    [env.win_tile] if env.win_tile is not None else [])
        return result


class WebHandler(SimpleHTTPRequestHandler):
    """Serve Qinghe, private practice tables and shared multiplayer rooms."""

    sessions: dict[str, WebTable | None] = {}
    session_seen: dict[str, float] = {}
    session_lock = threading.RLock()
    rooms = RoomRegistry()
    access_authorization = b''
    trusted_identity_issuer = ''
    record_store: HandStore | None = None

    def __init__(self, request, client_address, server):
        # Cookies ignore ports: isolate local test servers from the user's live table.
        self.cookie_name = f'qinghe_{server.server_port}'
        self.access_cookie = f'qinghe_access_{server.server_port}'
        self.sid = ''
        self.new_identity = False
        super().__init__(request, client_address, server, directory=str(WEB_ROOT))

    def parse_request(self) -> bool:
        """Check access before dispatching any HTTP method or allocating a game."""
        if not super().parse_request():
            return False
        # A keep-alive connection may carry requests from different authenticated accounts.
        self.sid = ''
        self.new_identity = False
        self.player_id = None
        self.account_subject = ''
        supplied = self.headers.get('Authorization', '').encode('utf-8')
        if self.trusted_identity_issuer:
            subjects = self.headers.get_all('X-Qinghe-Subject', [])
            if (not self.access_authorization
                    or not secrets.compare_digest(supplied, self.access_authorization)
                    or len(subjects) != 1 or not 1 <= len(subjects[0]) <= 255
                    or any(not 33 <= ord(char) <= 126 or char == ',' for char in subjects[0])):
                self.send_response(401)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', '0')
                self.end_headers()
                self.close_connection = True
                return False
            self.account_subject = subjects[0]
            return True
        if not self.access_authorization:
            return True
        path = urlsplit(self.path).path
        if self.command == 'POST' and path == '/access/login':
            self.access_login()
            return False
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except CookieError:
            cookies.clear()
        token = cookies[self.access_cookie].value if self.access_cookie in cookies else ''
        expires, _, signature = token.partition('.')
        valid_cookie = (expires.isascii() and expires.isdigit() and len(expires) <= 10
                        and time.time() < int(expires) <= time.time() + 86400
                        and signature.isascii()
                        and secrets.compare_digest(signature, self.access_signature(expires)))
        if not valid_cookie and not secrets.compare_digest(supplied, self.access_authorization):
            if self.command in ('GET', 'HEAD') and path in ('/', '/access/login'):
                self.access_form()
                return False
            self.send_response(401)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.end_headers()
            self.close_connection = True
            return False
        return True

    def access_signature(self, expires: str) -> str:
        """Sign the access expiry with the configured passcode."""
        return hmac.new(self.access_authorization, expires.encode(), 'sha256').hexdigest()

    def access_form(self, status: int = 200) -> None:
        """Show the passcode form without triggering a browser auth dialog."""
        page = (WEB_ROOT / 'access.html').read_text(encoding='utf-8')
        page = page.replace('<!--error-->', '通行碼不正確，請再試一次。' if status == 401 else '')
        payload = page.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(payload)
        self.close_connection = True

    def access_login(self) -> None:
        """Use a native HTML form and a signed cookie, without browser auth dialogs."""
        origin = self.headers.get('Origin')
        if (self.headers.get_content_type() != 'application/x-www-form-urlencoded' or
                (origin and urlsplit(origin).netloc != self.headers.get('Host'))):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 4096:
                raise ValueError
            password = parse_qs(self.rfile.read(length).decode('utf-8')).get('password', [''])[0]
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        supplied = b'Basic ' + base64.b64encode(f'friend:{password}'.encode('utf-8'))
        if not secrets.compare_digest(supplied, self.access_authorization):
            self.access_form(401)
            return
        expires = str(int(time.time()) + 86400)
        host = urlsplit('http://' + self.headers.get('Host', '')).hostname
        secure = '' if host in ('127.0.0.1', 'localhost', '::1') else '; Secure'
        self.send_response(303)
        self.send_header('Location', '/')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Set-Cookie',
                         f'{self.access_cookie}={expires}.{self.access_signature(expires)}; '
                         f'HttpOnly; SameSite=Strict; Path=/; Max-Age=86400{secure}')
        self.send_header('Content-Length', '0')
        self.end_headers()
        self.close_connection = True

    def send_head(self):
        """Serve only public files within the web root, including resolved links."""
        path = unquote(urlsplit(self.path).path)
        target = Path(self.translate_path(self.path)).resolve()
        if target.is_dir():
            for index in ('index.html', 'index.htm'):
                candidate = target / index
                if candidate.is_file():
                    target = candidate.resolve()
                    break
        if (any(part.startswith('.') for part in path.split('/') if part) or
                not target.is_relative_to(WEB_ROOT.resolve())):
            self.send_error(404)
            return None
        return super().send_head()

    def list_directory(self, path):
        self.send_error(404)
        return None

    def identity(self) -> str:
        """Resolve verified accounts before considering anonymous browser cookies."""
        if self.sid:
            return self.sid
        if self.trusted_identity_issuer:
            try:
                self.player_id = self.record_store.account_player_id(
                    self.trusted_identity_issuer, self.account_subject)
            except sqlite3.Error as error:
                raise RecordingError('玩家身分暫時無法保存，請稍後再試。') from error
            sid = 'account:' + self.player_id
        else:
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get('Cookie', ''))
            except CookieError:
                cookies.clear()
            sid = cookies[self.cookie_name].value if self.cookie_name in cookies else ''
            if self.record_store is not None and sid:
                self.player_id = self.record_store.browser_player_id(sid)
        with self.session_lock:
            now = time.monotonic()
            if sid not in self.sessions:
                if len(self.sessions) >= 1000:
                    for expired, seen in list(self.session_seen.items()):
                        if now - seen > 3600:
                            table = self.sessions.get(expired)
                            if table is not None:
                                with table.lock:
                                    table.interrupt_recording('session_expired')
                            self.sessions.pop(expired, None)
                            self.session_seen.pop(expired, None)
                    if len(self.sessions) >= 1000:
                        raise ValueError('目前連線已滿，請稍後再試。')
                if not self.trusted_identity_issuer and not self.player_id:
                    sid = secrets.token_urlsafe(24)
                    self.new_identity = True
                    if self.record_store is not None:
                        self.player_id = self.record_store.browser_player_id(sid, create=True)
                self.sessions[sid] = None
            self.session_seen[sid] = now
        self.sid = sid
        return sid

    def table(self) -> tuple[str, WebTable]:
        sid = self.identity()
        with self.session_lock:
            if self.sessions[sid] is None:
                heads = (self.record_store.practice_hands(self.player_id, heads=True)
                         if self.record_store and self.player_id else [])
                # Legacy records remain history, not abandoned resumable deals.
                heads = [head for head in heads if head['recovery_version'] is not None]
                if heads:
                    selected = self.record_store.selected_practice(self.player_id)
                    head = next((item for item in heads if item['table_id'] == selected), heads[-1])
                    documents = self.record_store.player_records(
                        self.player_id, hand_id=head['hand_id'])
                    from app.web_records import can_resume

                    if not can_resume(documents[0], self.record_store, self.player_id):
                        raise ValueError('原 Session 與目前版本不相容，請先查看牌局紀錄。')
                    self.sessions[sid] = WebTable.restore(documents[0], self.record_store)
                else:
                    self.sessions[sid] = WebTable(record_store=self.record_store,
                                                  player_id=self.player_id)
                if self.record_store and self.player_id:
                    self.record_store.select_practice(self.player_id, self.sessions[sid].table_id)
            return sid, self.sessions[sid]

    def respond(self, data: dict, sid: str, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        if sid and not self.trusted_identity_issuer:
            secure = '; Secure' if self.headers.get('X-Forwarded-Proto') == 'https' else ''
            self.send_header('Set-Cookie',
                             f'{self.cookie_name}={sid}; HttpOnly; SameSite=Strict; '
                             f'Max-Age=31536000; Path=/{secure}')
        try:
            self.end_headers()
            self.wfile.write(payload)
        except ConnectionError:
            pass  # A disconnected player will obtain a fresh snapshot on reconnect.

    def do_GET(self) -> None:
        path = urlsplit(self.path)
        if path.path not in ('/api/state', '/api/room/state', '/api/history', '/api/replay',
                             '/api/sessions', '/api/session'):
            super().do_GET()
            return
        sid = ''
        try:
            if path.path in ('/api/history', '/api/replay', '/api/sessions', '/api/session'):
                from app.web_records import (
                    history, replay_frames, practice_summary, practice_statistics,
                )

                sid = self.identity()
                if self.record_store is None or self.player_id is None:
                    raise ValueError('目前未啟用牌譜保存。')
                if path.path == '/api/sessions':
                    data = {'sessions': [practice_summary(head) for head in reversed(
                        self.record_store.practice_hands(self.player_id, heads=True))]}
                elif path.path == '/api/session':
                    table_id = parse_qs(path.query).get('session_id', [''])[0]
                    data = practice_statistics(self.record_store, self.player_id, table_id)
                elif path.path == '/api/history':
                    data = {'hands': history(self.record_store, self.player_id)}
                else:
                    hand_id = parse_qs(path.query).get('hand_id', [''])[0]
                    documents = self.record_store.player_records(self.player_id, hand_id=hand_id)
                    if not documents:
                        raise ValueError('找不到你的牌局紀錄。')
                    view = parse_qs(path.query).get('view', [None])[0]
                    viewer = None if view is None else int(view)
                    data = {'frames': replay_frames(documents[0], self.player_id, viewer)}
                self.respond(data, sid)
            elif path.path == '/api/state':
                sid = self.identity()
                try:
                    room = self.rooms.get(sid)
                except ValueError:
                    sid, table = self.table()
                    with table.lock:
                        data = table.snapshot()
                else:
                    with room.changed:
                        room.touch(sid)
                        data = room.snapshot(sid)
                self.respond(data, sid)
            else:
                sid = self.identity()
                room = self.rooms.get(sid)
                after = int(parse_qs(path.query).get('after', ['-1'])[0])
                with room.changed:
                    room.touch(sid)
                    if after == room.version:
                        room.changed.wait(timeout=20)
                    room.touch(sid)
                    data = room.snapshot(sid)
                self.respond(data, sid)
        except (RecordingError, sqlite3.Error, OSError) as error:
            self.respond({'error': str(error)}, sid, 503)
        except (ValueError, TypeError) as error:
            self.respond({'error': str(error)}, sid, 400)

    def do_POST(self) -> None:
        if self.path not in ('/api/action', '/api/new', '/api/next', '/api/rooms',
                             '/api/room/join', '/api/room/start', '/api/room/action',
                             '/api/room/next', '/api/room/leave', '/api/preferences',
                             '/api/player/name', '/api/resume'):
            self.send_error(404)
            return
        sid = ''
        try:
            origin = self.headers.get('Origin')
            if (self.headers.get_content_type() != 'application/json' or
                    (origin and urlsplit(origin).netloc != self.headers.get('Host'))):
                raise ValueError('無效請求來源。')
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 4096:
                raise ValueError('無效請求')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('無效請求')
            if self.path == '/api/resume':
                from app.web_records import can_resume, viewer_seat

                sid = self.identity()
                if self.record_store is None or self.player_id is None:
                    raise ValueError('目前未啟用牌譜保存。')
                hand_id = body.get('hand_id')
                if not isinstance(hand_id, str):
                    raise ValueError('無效牌局。')
                documents = self.record_store.player_records(self.player_id, hand_id=hand_id)
                if not documents or not can_resume(documents[0], self.record_store, self.player_id):
                    raise ValueError('這份牌譜無法續局，或已有更新的牌局。')
                document = documents[0]
                if document['metadata']['source'] == 'multiplayer':
                    room = self.rooms.recover(sid, self.player_id, document,
                        lambda record: WebTable.restore(record, self.record_store),
                        store=self.record_store)
                    with room.changed:
                        data = room.snapshot(sid)
                else:
                    if viewer_seat(document, self.player_id, current=True) != 0:
                        raise ValueError('只能恢復自己的練習桌。')
                    try:
                        self.rooms.get(sid)
                    except ValueError:
                        pass
                    else:
                        raise ValueError('請先離開目前房間。')
                    with self.session_lock:
                        document = self.record_store.player_records(
                            self.player_id, hand_id=hand_id)[0]
                        if not can_resume(document, self.record_store, self.player_id):
                            raise ValueError('此 Session 已有更新進度，請重新開啟紀錄。')
                        current = self.sessions.get(sid)
                        if (current is None or current.recording_error or
                                current.table_id != document['metadata']['table_id']):
                            restored = WebTable.restore(document, self.record_store)
                            self.sessions[sid] = restored
                        table = self.sessions[sid]
                        self.record_store.select_practice(self.player_id, table.table_id)
                        with table.lock:
                            table.advance()
                            data = table.snapshot()
                self.respond(data, sid)
                return
            if self.path == '/api/player/name':
                name = player_name(body.get('name'))
                if not name:
                    raise ValueError('請輸入顯示名稱。')
                sid = self.identity()
                try:
                    room = self.rooms.get(sid)
                except ValueError:
                    with self.session_lock:
                        sid, table = self.table()
                        with table.lock:
                            table.check_recording()
                            table.record_seat(0, {**table.record_players[0], 'name': name})
                            data = table.snapshot()
                else:
                    with room.changed:
                        room.rename(sid, name)
                        data = room.snapshot(sid)
                self.respond(data, sid)
                return
            if self.path == '/api/preferences':
                enabled = body.get('auto_ting_discard')
                if type(enabled) is not bool:
                    raise ValueError('聽牌自動出牌設定必須為開啟或關閉。')
                sid = self.identity()
                try:
                    room = self.rooms.get(sid)
                except ValueError:
                    with self.session_lock:
                        sid, table = self.table()
                        with table.lock:
                            table.auto_ting_discard[0] = enabled
                            playback = []
                            table.advance(playback)
                            data = {**table.snapshot(), 'playback': playback}
                else:
                    with room.changed:
                        pid = room.touch(sid)
                        room.table.auto_ting_discard[pid] = enabled
                        data = room.snapshot(sid)
                self.respond(data, sid)
                return
            if self.path.startswith('/api/room'):
                sid = self.identity()
                if self.path == '/api/rooms':
                    room = self.rooms.create(
                        sid, lambda **kwargs: WebTable(
                            **kwargs, record_store=self.record_store, defer_recording=True),
                        body.get('name', ''), player_id=self.player_id)
                elif self.path == '/api/room/join':
                    code = body.get('code')
                    if not isinstance(code, str) or len(code) != 8:
                        raise ValueError('請輸入八碼房號。')
                    room = self.rooms.join(sid, code.upper(), body.get('name', ''),
                                           player_id=self.player_id)
                elif self.path == '/api/room/leave':
                    self.rooms.leave(sid)
                    self.respond({'left': True}, sid)
                    return
                else:
                    room = self.rooms.get(sid)
                    with room.changed:
                        if self.path in ('/api/room/start', '/api/room/next'):
                            room.start(sid, next_hand=self.path.endswith('/next'))
                        else:
                            if type(body.get('version')) is not int:
                                raise ValueError('無效牌局版本。')
                            room.act(sid, body['version'], body.get('request_id'),
                                     body.get('action'))
                with room.changed:
                    data = room.snapshot(sid)
                self.respond(data, sid)
                return
            with self.session_lock:
                sid, table = self.table()
                with table.lock:
                    expected = self.headers.get('X-Qinghe-Session')
                    if expected and expected != table.table_id:
                        raise ValueError('牌桌已在其他分頁切換，請重新整理後操作。')
                    if self.path == '/api/new':
                        if not table.env.done:
                            raise ValueError('本局尚未結束，請先打完再開新 Session。')
                        if self.record_store and self.player_id:
                            heads = self.record_store.practice_hands(self.player_id, heads=True)
                            if any(head['recovery_version'] is not None and
                                   head['status'] != 'completed' for head in heads):
                                raise ValueError('另有尚未打完的單人牌局，請從紀錄返回完成。')
                        table.new_table()
                        if self.record_store and self.player_id:
                            self.record_store.select_practice(self.player_id, table.table_id)
                        data = table.snapshot()
                    elif self.path == '/api/next':
                        data = table.next_hand()
                    else:
                        data = table.act(body)
                    self.respond(data, sid)
        except (RecordingError, sqlite3.Error, OSError) as error:
            self.respond({'error': str(error)}, sid, 503)
        except (ValueError, TypeError, KeyError) as error:
            self.respond({'error': str(error)}, sid, 400)

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)


def main() -> None:
    """Start Qinghe; expose only behind an HTTPS reverse proxy for internet play."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--record-db', type=Path, default=Path('data/hands.sqlite3'),
                        help='Private SQLite hand records, outside the public web root.')
    parser.add_argument('--access-password-file', type=Path,
                        help='Protect all requests with a passcode read from this file.')
    parser.add_argument('--trusted-identity-issuer', default='',
                        help='Trust the private gateway subject only with its Basic credential.')
    args = parser.parse_args()
    if args.trusted_identity_issuer and not args.access_password_file:
        parser.error('--trusted-identity-issuer requires --access-password-file')
    WebHandler.trusted_identity_issuer = args.trusted_identity_issuer
    if args.access_password_file:
        try:
            password = args.access_password_file.read_text(encoding='utf-8').strip()
        except (OSError, UnicodeError):
            parser.error('Cannot read access password file.')
        if len(password) < 16:
            parser.error('Access password must contain at least 16 characters.')
        WebHandler.access_authorization = b'Basic ' + base64.b64encode(
            f'friend:{password}'.encode('utf-8'))
    try:
        WebHandler.record_store = HandStore(args.record_db)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.error(f'Cannot open hand-record database: {error}')
    try:
        server = ThreadingHTTPServer((args.host, args.port), WebHandler)
    except OSError:
        WebHandler.record_store.close()
        raise
    server.daemon_threads = False
    stop = threading.Event()
    scheduler = threading.Thread(target=WebHandler.rooms.run, args=(stop,), daemon=True)
    scheduler.start()
    print(f'青禾麻將：http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        scheduler.join()
        server.server_close()
        WebHandler.record_store.close()


if __name__ == '__main__':
    main()
