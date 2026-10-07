"""Local browser table backed by the existing Taiwan Mahjong rules engine."""
from __future__ import annotations

import argparse
import base64
import hmac
from copy import deepcopy
import json
import secrets
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from app.web_rooms import RoomRegistry

from domain.gameplay.game_env import Mahjong16Env
from domain.rules.ruleset import Ruleset
from bots.greedy import GreedyBotStrategy
from app.table import TableManager, TableState
from domain.analysis import visible_count_global
from domain.rules.hands import waits_for_hand_16
from domain.scoring.engine import compute_payments, score_with_breakdown
from domain.scoring.lookup import load_scoring_assets
from domain.scoring.score_types import ScoringContext

WEB_ROOT = Path(__file__).resolve().parents[1] / 'ui' / 'web'


class WebTable:
    """Engine-backed table with private viewer snapshots and legal human actions."""

    def __init__(self, seed: int | None = None, human_pids: set[int] | None = None):
        self.human_pids = {0} if human_pids is None else set(human_pids)
        self.auto_ting_discard = [True] * 4
        self.env = Mahjong16Env(Ruleset(randomize_seating_and_dealer=False), seed=seed)
        self.bot = GreedyBotStrategy()
        self.events: list[dict] = []
        self.lock = threading.Lock()
        self.scoring = load_scoring_assets(
            self.env.rules.scoring_profile, self.env.rules.scoring_overrides_path
        )
        self.new_table()

    def new_table(self) -> None:
        """Start a fresh practice table with fixed initial seats and 1,000 points each."""
        self.manager = TableManager(self.env.rules, seed=self.env.reset_rng_seed)
        self.manager.state = TableState(
            seat_winds=['E', 'S', 'W', 'N'], seating_order=[0, 1, 2, 3]
        )
        self.totals = [1000] * self.env.rules.n_players
        self.round = 0
        self.start_hand()

    def start_hand(self, playback: list | None = None) -> None:
        """Deal the next hand using the shared dealer and round-wind manager."""
        self.round += 1
        self.events = []
        self.settlement = None
        self.manager.start_hand(self.env)
        self.advance(playback)

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
        self.manager.finish_hand(self.env)

    def actor(self) -> int:
        """Return the turn actor or first unanswered seat for sequential clients."""
        if self.env.phase == 'REACTION':
            return self.env.reaction_queue[self.env.reaction_idx]
        return self.env.turn

    def apply(
        self, action: dict, playback: list | None = None, pid: int | None = None
    ) -> None:
        """Apply and record an already validated action."""
        pid, phase = self.actor() if pid is None else pid, self.env.phase
        _, _, _, info = self.env.step(action, pid=pid)
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
                self.apply(action, playback, pid=automatic)
                continue
            pid = self.actor()
            actions = self.env.legal_actions(pid)
            ting_discard = self.ting_discard() if auto_discard_ting else None
            if ting_discard is not None:
                self.apply(ting_discard, playback)
                continue
            if pid in self.human_pids:
                if actions == [{'type': 'PASS'}]:
                    self.apply(actions[0], playback)
                    continue
                return
            action = self.bot.choose(self.env._obs(pid))
            if self.env.phase == 'TURN':
                self.record_frame(playback, pid, 'THINK')
            self.apply(action, playback)
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
        env = self.env
        result = deepcopy(env._obs(viewer))
        result.update({
            'auto_ting_discard': self.auto_ting_discard[viewer],
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
            'seat_winds': list(env.seat_winds), 'seating_order': list(env.seating_order),
            'dealer_streak': env.dealer_streak, 'totals': list(self.totals),
            'settlement': self.settlement,
            'remaining': max(0, len(env.wall) - env._dead_wall_reserved()),
            'players': [{'count': len(p.hand) + int(p.drawn is not None),
                         'has_drawn': p.drawn is not None,
                         'flowers': list(p.flowers), 'melds': deepcopy(p.melds),
                         'ting': p.declared_ting} for p in env.players],
        })
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
    session_lock = threading.Lock()
    rooms = RoomRegistry()
    access_authorization = b''

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
        if not self.access_authorization:
            return True
        path = urlsplit(self.path).path
        if self.command == 'POST' and path == '/access/login':
            self.access_login()
            return False
        supplied = self.headers.get('Authorization', '').encode('utf-8')
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
        if self.sid:
            return self.sid
        cookies = SimpleCookie()
        cookies.load(self.headers.get('Cookie', ''))
        sid = cookies[self.cookie_name].value if self.cookie_name in cookies else ''
        with self.session_lock:
            now = time.monotonic()
            if sid not in self.sessions:
                if len(self.sessions) >= 1000:
                    for expired, seen in list(self.session_seen.items()):
                        if now - seen > 3600:
                            self.sessions.pop(expired, None)
                            self.session_seen.pop(expired, None)
                    if len(self.sessions) >= 1000:
                        raise ValueError('目前連線已滿，請稍後再試。')
                sid = secrets.token_urlsafe(24)
                self.sessions[sid] = None
                self.new_identity = True
            self.session_seen[sid] = now
        self.sid = sid
        return sid

    def table(self) -> tuple[str, WebTable]:
        sid = self.identity()
        with self.session_lock:
            if self.sessions[sid] is None:
                self.sessions[sid] = WebTable()
            return sid, self.sessions[sid]

    def respond(self, data: dict, sid: str, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        if sid and self.new_identity:
            secure = '; Secure' if self.headers.get('X-Forwarded-Proto') == 'https' else ''
            self.send_header('Set-Cookie',
                             f'{self.cookie_name}={sid}; HttpOnly; SameSite=Strict; Path=/{secure}')
        try:
            self.end_headers()
            self.wfile.write(payload)
        except ConnectionError:
            pass  # A disconnected player will obtain a fresh snapshot on reconnect.

    def do_GET(self) -> None:
        path = urlsplit(self.path)
        if path.path not in ('/api/state', '/api/room/state'):
            super().do_GET()
            return
        sid = ''
        try:
            if path.path == '/api/state':
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
        except (ValueError, TypeError) as error:
            self.respond({'error': str(error)}, sid, 400)

    def do_POST(self) -> None:
        if self.path not in ('/api/action', '/api/new', '/api/next', '/api/rooms',
                             '/api/room/join', '/api/room/start', '/api/room/action',
                             '/api/room/next', '/api/room/leave', '/api/preferences'):
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
            if self.path == '/api/preferences':
                enabled = body.get('auto_ting_discard')
                if type(enabled) is not bool:
                    raise ValueError('聽牌自動出牌設定必須為開啟或關閉。')
                sid = self.identity()
                try:
                    room = self.rooms.get(sid)
                except ValueError:
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
                    room = self.rooms.create(sid, WebTable, body.get('name', ''))
                elif self.path == '/api/room/join':
                    code = body.get('code')
                    if not isinstance(code, str) or len(code) != 8:
                        raise ValueError('請輸入八碼房號。')
                    room = self.rooms.join(sid, code.upper(), body.get('name', ''))
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
            sid, table = self.table()
            with table.lock:
                if self.path == '/api/new':
                    table.new_table()
                    data = table.snapshot()
                elif self.path == '/api/next':
                    data = table.next_hand()
                else:
                    data = table.act(body)
                self.respond(data, sid)
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
    parser.add_argument('--access-password-file', type=Path,
                        help='Protect all requests with a passcode read from this file.')
    args = parser.parse_args()
    if args.access_password_file:
        try:
            password = args.access_password_file.read_text(encoding='utf-8').strip()
        except (OSError, UnicodeError):
            parser.error('Cannot read access password file.')
        if len(password) < 16:
            parser.error('Access password must contain at least 16 characters.')
        WebHandler.access_authorization = b'Basic ' + base64.b64encode(
            f'friend:{password}'.encode('utf-8'))
    server = ThreadingHTTPServer((args.host, args.port), WebHandler)
    server.daemon_threads = True
    stop = threading.Event()
    scheduler = threading.Thread(target=WebHandler.rooms.run, args=(stop,), daemon=True)
    scheduler.start()
    print(f'青禾麻將：http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
