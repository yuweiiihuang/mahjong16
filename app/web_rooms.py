"""Shared, server-authoritative rooms for the Qinghe browser table."""
from __future__ import annotations

from copy import deepcopy
import secrets
import threading
import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.web import WebTable


def player_name(value: str) -> str:
    """Validate a display name before changing a room or reserving a seat."""
    if not isinstance(value, str):
        raise ValueError('玩家名稱必須是文字。')
    name = value.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError('玩家名稱不能包含換行或控制字元。')
    return name


class WebRoom:
    """One table with private seats, revision checks and bounded reconnect grace."""

    RECONNECT_SECONDS = 90

    def __init__(self, code: str, owner: str, table: WebTable, name: str = '') -> None:
        self.code = code
        self.table = table
        self.seats: list[str | None] = [owner, None, None, None]
        self.names = {owner: player_name(name) or '玩家 1'}
        self.seen = {owner: time.monotonic()}
        self.owner = owner
        self.started = False
        self.version = 0
        self.event = None
        self.ready_at = 0.0
        self.thinking = False
        self.last_active = time.monotonic()
        self.requests: dict[tuple[str, str], int] = {}
        self.changed = threading.Condition()

    def publish(self) -> None:
        """Wake waiting clients after an authoritative change (lock must be held)."""
        self.version += 1
        self.changed.notify_all()

    def join(self, sid: str, name: str = '') -> None:
        """Take an unreserved bot seat without changing its game state, or reconnect."""
        name = player_name(name)
        if sid not in self.seats:
            if None not in self.seats:
                raise ValueError('房間已滿。')
            seat = self.seats.index(None)
            self.seats[seat] = sid
            self.names[sid] = name or f'玩家 {seat + 1}'
            if not self.owner:
                self.owner = sid
            if self.thinking and self.event == {'pid': seat, 'type': 'THINK'}:
                self.thinking = False
                self.event = None
                self.ready_at = 0
            self.publish()
        self.touch(sid)

    def touch(self, sid: str) -> int:
        """Renew a member's reconnect grace and return the authoritative seat."""
        if sid not in self.seats:
            raise ValueError('你尚未加入這個房間。')
        self.last_active = self.seen[sid] = time.monotonic()
        return self.seats.index(sid)

    def snapshot(self, sid: str) -> dict:
        """Rotate only player indices, so every browser keeps its own seat at zero."""
        viewer = self.seats.index(sid)
        state = self.table.snapshot(viewer)
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
        now = time.monotonic()
        state['room'] = {
            'code': self.code, 'started': self.started, 'host': sid == self.owner,
            'members': [
                {'name': (self.names[self.seats[pid]] if self.seats[pid] else
                          ['電腦玩家', '陳予安', '林小滿', '周子墨'][pid]),
                 'human': self.seats[pid] is not None,
                 'connected': (self.seats[pid] is not None and
                               now - self.seen.get(self.seats[pid], 0) < 30)}
                for pid in order
            ],
        }
        state['version'] = self.version
        state['display_event'] = (None if not self.event else
                                  {**self.event, 'pid': relative(self.event['pid'])})
        if not self.started or now < self.ready_at:
            state['legal_actions'] = []
            state['ting_options'] = []
        if not self.started:
            state.update(hand=[], drawn=None, flowers=[], melds=[], remaining=0, actor=None)
            state['melds_all'] = [[], [], [], []]
            state['rivers'] = [[], [], [], []]
            for player in state['players']:
                player.update(count=0, has_drawn=False, flowers=[], melds=[])
        return state

    def start(self, sid: str, next_hand: bool = False) -> None:
        """Let the host deal, or advance after the current hand has settled."""
        self.touch(sid)
        if sid != self.owner:
            raise ValueError('請由房主開局。')
        if next_hand:
            if not self.started or not self.table.env.done:
                raise ValueError('本局尚未結束。')
            self.table.next_hand()
        elif self.started:
            raise ValueError('本桌已開局。')
        else:
            self.table.new_table()
        self.started = True
        self.event = None
        self.thinking = False
        self.ready_at = time.monotonic() + .5
        self.publish()

    def act(self, sid: str, version: int, request_id: str, action: dict) -> None:
        """Apply a legal current-seat action once; acknowledge already accepted retries."""
        pid = self.touch(sid)
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
            raise ValueError('無效操作編號。')
        if (sid, request_id) in self.requests:
            return  # Retries acknowledge the original move without applying it twice.
        if (not self.started or self.table.env.done or version != self.version or
                time.monotonic() < self.ready_at or
                (self.table.env.phase != 'REACTION' and self.table.actor() != pid) or
                action not in self.table.env.legal_actions(pid)):
            raise ValueError('牌局已更新，請重新選擇操作。')
        self.apply(action, pid=pid)
        self.requests[(sid, request_id)] = self.version
        if len(self.requests) > 256:
            self.requests.pop(next(iter(self.requests)))

    def apply(self, action: dict, pid: int | None = None) -> None:
        """Apply a validated move, settle forced passes and publish its resolved event."""
        collecting = self.table.env.phase == 'REACTION'
        pid = self.table.actor() if pid is None else pid
        frames = []
        self.table.apply(action, frames, pid=pid)
        # Automatic ting discards run in tick, preserving the shared action delay.
        self.table.advance(frames, auto_discard_ting=False)
        if collecting and self.table.env.phase == 'REACTION':
            # A private reply does not change the shared revision or wake other seats.
            # Other replies based on this same discard remain valid.
            return
        self.event = {'pid': frames[-1]['pid'], 'type': frames[-1]['type']} if frames else None
        self.thinking = False
        self.ready_at = time.monotonic() + (.65 if self.event else .1)
        self.publish()

    def tick(self, now: float) -> None:
        """Run one bot step after a shared thinking/action delay, including disconnects."""
        if self.owner and now - self.seen.get(self.owner, now) >= self.RECONNECT_SECONDS:
            replacement = next((sid for sid in self.seats if sid and sid != self.owner
                                and now - self.seen.get(sid, 0) < 30), None)
            if replacement:
                self.owner = replacement
                self.publish()
        if not self.started or self.table.env.done or now < self.ready_at:
            return
        if self.ready_at and not self.thinking:
            self.ready_at = 0
            self.event = None
            self.publish()
        pid = self.table.actor()
        ting_discard = self.table.ting_discard()
        if ting_discard is not None:
            self.apply(ting_discard, pid=pid)
            return
        if self.table.env.phase == 'REACTION':
            pid = next((candidate for candidate in self.table.env.pending_reactions()
                        if self.seats[candidate] is None
                        or now - self.seen.get(self.seats[candidate], 0)
                        >= self.RECONNECT_SECONDS), None)
            if pid is None:
                return
        sid = self.seats[pid]
        if sid and now - self.seen.get(sid, now) < self.RECONNECT_SECONDS:
            return
        if not self.thinking and self.table.env.phase == 'TURN':
            self.event = {'pid': pid, 'type': 'THINK'}
            self.thinking = True
            self.ready_at = now + .7
            self.publish()
            return
        self.apply(self.table.bot.choose(self.table.env._obs(pid)), pid=pid)


class RoomRegistry:
    """Bounded in-memory rooms; one scheduler services all tables."""

    def __init__(self) -> None:
        self.rooms: dict[str, WebRoom] = {}
        self.memberships: dict[str, str] = {}
        self.lock = threading.Lock()

    def create(self, sid: str, table_factory: Callable[..., WebTable],
               name: str = '') -> WebRoom:
        """Create one invitation-only room for an identity without a current room."""
        name = player_name(name)
        with self.lock:
            if sid in self.memberships:
                raise ValueError('請先離開目前房間。')
            if len(self.rooms) >= 100:
                raise ValueError('目前房間已滿，請稍後再試。')
            code = secrets.token_hex(4).upper()
            while code in self.rooms:
                code = secrets.token_hex(4).upper()
            room = WebRoom(code, sid, table_factory(human_pids={0, 1, 2, 3}), name)
            self.rooms[code] = room
            self.memberships[sid] = code
            return room

    def join(self, sid: str, code: str, name: str = '') -> WebRoom:
        """Join a free seat without assigning one identity to multiple rooms."""
        with self.lock:
            room = self.rooms.get(code)
            if room is None:
                raise ValueError('找不到房間，可能已結束。')
            if sid in self.memberships and self.memberships[sid] != code:
                raise ValueError('請先離開目前房間。')
            with room.changed:
                room.join(sid, name)
            self.memberships[sid] = code
            return room

    def get(self, sid: str) -> WebRoom:
        """Return a member's room without accepting a client-supplied seat identity."""
        with self.lock:
            room = self.rooms.get(self.memberships.get(sid))
            if room is None:
                raise ValueError('你尚未加入房間，或房間已結束。')
            return room

    def leave(self, sid: str) -> None:
        """Vacate a seat for a bot and transfer host ownership if needed."""
        with self.lock:
            room = self.rooms.get(self.memberships.pop(sid, None))
            if room:
                with room.changed:
                    room.seats[room.seats.index(sid)] = None
                    room.seen.pop(sid, None)
                    room.names.pop(sid, None)
                    if room.owner == sid:
                        room.owner = next((s for s in room.seats if s), '')
                    room.publish()

    def run(self, stop: threading.Event) -> None:
        """Schedule bot turns and expire empty or idle rooms until shutdown."""
        # ponytail: single-process rooms; use a shared store before adding server replicas.
        while not stop.wait(.1):
            now = time.monotonic()
            with self.lock:
                for code, room in list(self.rooms.items()):
                    with room.changed:
                        if now - room.last_active > 3600 or not any(room.seats):
                            for sid in room.seats:
                                self.memberships.pop(sid, None)
                            del self.rooms[code]
                            continue
                        room.tick(now)
