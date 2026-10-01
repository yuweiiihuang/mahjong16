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
from app.table import TableManager, TableState
from domain.analysis import visible_count_global
from domain.rules.hands import waits_for_hand_16
from domain.scoring.engine import compute_payments, score_with_breakdown
from domain.scoring.lookup import load_scoring_assets
from domain.scoring.score_types import ScoringContext

WEB_ROOT = Path(__file__).resolve().parents[1] / 'ui' / 'web'


class WebTable:
    """One private practice table; only legal human actions cross the HTTP boundary."""

    def __init__(self, seed: int | None = None):
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

    def start_hand(self) -> None:
        """Deal the next hand using the shared dealer and round-wind manager."""
        self.round += 1
        self.events = []
        self.settlement = None
        self.manager.start_hand(self.env)
        self.advance()

    def next_hand(self) -> dict:
        """Continue a completed hand without clearing accumulated points."""
        if not self.env.done:
            raise ValueError('本局尚未結束。')
        self.start_hand()
        return self.snapshot()

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
        self.settle()

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
            'round': self.round, 'quan_feng': env.quan_feng,
            'seat_winds': list(env.seat_winds), 'seating_order': list(env.seating_order),
            'dealer_streak': env.dealer_streak, 'totals': list(self.totals),
            'settlement': self.settlement,
            'remaining': max(0, len(env.wall) - env._dead_wall_reserved()),
            'players': [{'count': len(p.hand) + int(p.drawn is not None),
                         'flowers': list(p.flowers), 'melds': p.melds,
                         'ting': p.declared_ting} for p in env.players],
        })
        # Unseen counts use only the human hand and public tiles, never the wall or bots.
        visible = {**result, 'melds_all': [
            [meld for meld in melds if pid == 0 or meld['type'] != 'ANGANG']
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
        )) if result['declared_ting'] and not env.done else []
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
        if self.path not in ('/api/action', '/api/new', '/api/next'):
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
                    table.new_table()
                    data = table.snapshot()
                elif self.path == '/api/next':
                    data = table.next_hand()
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
