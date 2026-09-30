"""Local browser table backed by the existing Taiwan Mahjong rules engine."""
from __future__ import annotations

import argparse
import json
import secrets
import threading
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from domain.gameplay.game_env import Mahjong16Env
from domain.rules.ruleset import Ruleset
from bots.greedy import GreedyBotStrategy

WEB_ROOT = Path(__file__).resolve().parents[1] / 'ui' / 'web'


class WebTable:
    """One private practice table; only legal human actions cross the HTTP boundary."""

    def __init__(self, seed: int | None = None):
        self.env = Mahjong16Env(Ruleset(randomize_seating_and_dealer=False), seed=seed)
        self.bot = GreedyBotStrategy()
        self.events: list[dict] = []
        self.lock = threading.Lock()
        self.env.reset()
        self.advance()

    def actor(self) -> int:
        """Return the actual actor for a turn or sequential reaction window."""
        if self.env.phase == 'REACTION':
            return self.env.reaction_queue[self.env.reaction_idx]
        return self.env.turn

    def apply(self, action: dict) -> None:
        """Apply and record an already validated action."""
        self.events.append({'pid': self.actor(), **action})
        self.events = self.events[-60:]
        self.env.step(action)

    def advance(self) -> None:
        """Play bots until a meaningful human choice or round end."""
        while not self.env.done:
            pid = self.actor()
            actions = self.env.legal_actions(pid)
            if pid == 0:
                if actions == [{'type': 'PASS'}]:
                    self.apply(actions[0])
                    continue
                return
            self.apply(self.bot.choose(self.env._obs(pid)))

    def act(self, action: dict) -> dict:
        """Reject stale/forged moves before mutating game state."""
        if self.env.done or self.actor() != 0 or action not in self.env.legal_actions(0):
            raise ValueError('這個操作已失效，請重新選牌。')
        self.apply(action)
        self.advance()
        return self.snapshot()

    def snapshot(self) -> dict:
        """Expose public table state and the human hand, never opponent hands."""
        env = self.env
        result = env._obs(0)
        result.update({
            'legal_actions': [] if env.done else env.legal_actions(0),
            'actor': None if env.done else self.actor(), 'done': env.done,
            'winner': env.winner, 'win_source': env.win_source,
            'dealer': env.dealer_pid, 'events': self.events,
            'remaining': max(0, len(env.wall) - env._dead_wall_reserved()),
            'players': [{'count': len(p.hand) + int(p.drawn is not None),
                         'flowers': list(p.flowers), 'melds': p.melds,
                         'ting': p.declared_ting} for p in env.players],
        })
        if env.done and env.winner is not None:
            winner = env.players[env.winner]
            result['winning_hand'] = sorted(winner.hand) + (
                [env.win_tile] if env.win_tile is not None else [])
        return result


class WebHandler(SimpleHTTPRequestHandler):
    """Serve the app and cookie-isolated practice tables on localhost."""

    sessions: dict[str, WebTable] = {}
    session_lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def table(self) -> tuple[str, WebTable]:
        cookies = SimpleCookie()
        cookies.load(self.headers.get('Cookie', ''))
        sid = cookies['table'].value if 'table' in cookies else ''
        with self.session_lock:
            if sid not in self.sessions:
                sid = secrets.token_urlsafe(24)
                self.sessions[sid] = WebTable()
        return sid, self.sessions[sid]

    def respond(self, data: dict, sid: str, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Set-Cookie', f'table={sid}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == '/api/state':
            sid, table = self.table()
            with table.lock:
                self.respond(table.snapshot(), sid)
        else:
            super().do_GET()

    def do_POST(self) -> None:
        if self.path not in ('/api/action', '/api/new'):
            self.send_error(404)
            return
        sid, table = self.table()
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 4096:
                raise ValueError('無效請求')
            body = json.loads(self.rfile.read(length))
            with table.lock:
                if self.path == '/api/new':
                    table.env.reset()
                    table.events = []
                    table.advance()
                    data = table.snapshot()
                else:
                    data = table.act(body)
                self.respond(data, sid)
        except (ValueError, TypeError, KeyError) as error:
            self.respond({'error': str(error)}, sid, 400)


def main() -> None:
    """Start a local-only practice web server."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), WebHandler)
    print(f'青禾麻將：http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
