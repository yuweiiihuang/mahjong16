"""Shared, server-authoritative rooms for the Qinghe browser table."""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import secrets
import threading
import time
from uuid import uuid4
from typing import TYPE_CHECKING, Callable
from app.hand_store import RecordingError
from app.web_view import relative_snapshot

if TYPE_CHECKING:
    from app.hand_store import HandStore
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

    def __init__(self, code: str, owner: str, table: WebTable, name: str = '', *,
                 player_id: str | None = None) -> None:
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
        self.record_ids = {owner: player_id or str(uuid4())}
        self.table.record_source = 'multiplayer'
        self.table.room_checkpoint = self.recovery_state

    def recovery_state(self) -> dict:
        """Save seat ownership with the engine prefix, never browser credentials."""
        return {'code': self.code, 'owner': self.record_ids.get(self.owner),
                'version': self.version,
                'requests': [list(key) for key in self.requests],
                'seats': [self.record_ids.get(sid) if sid else None for sid in self.seats],
                'names': [self.names.get(sid, '') for sid in self.seats]}

    def record_seat(self, pid: int) -> None:
        """Keep private pseudonyms separate from cookie credentials and display names."""
        sid = self.seats[pid]
        if sid and sid not in self.record_ids:
            self.record_ids[sid] = str(uuid4())
        self.table.record_seat(pid, {
            'player_id': self.record_ids[sid] if sid else None,
            'name': self.names[sid] if sid else '電腦玩家', 'human': sid is not None,
        })

    def publish(self) -> None:
        """Wake waiting clients after an authoritative change (lock must be held)."""
        self.version += 1
        self.changed.notify_all()

    def join(self, sid: str, name: str = '', *, player_id: str | None = None) -> None:
        """Take an unreserved bot seat without changing its game state, or reconnect."""
        self.table.check_recording()
        name = player_name(name)
        reserved = next((member for member in self.seats if member != sid and member and
                         self.record_ids.get(member) == player_id and player_id), None)
        if reserved:
            seat = self.seats.index(reserved)
            self.seats[seat] = sid
            self.names[sid] = self.names.pop(reserved)
            self.record_ids[sid] = self.record_ids.pop(reserved)
            self.seen.pop(reserved, None)
            if self.owner == reserved:
                self.owner = sid
            self.publish()
        if sid not in self.seats:
            if None not in self.seats:
                raise ValueError('房間已滿。')
            seat = self.seats.index(None)
            self.seats[seat] = sid
            self.names[sid] = name or f'玩家 {seat + 1}'
            self.record_ids[sid] = player_id or str(uuid4())
            if self.started:
                try:
                    self.record_seat(seat)
                except RecordingError:
                    self.seats[seat] = None
                    self.names.pop(sid)
                    self.record_ids.pop(sid, None)
                    self.publish()
                    raise
            if not self.owner:
                self.owner = sid
            if self.thinking and self.event == {'pid': seat, 'type': 'THINK'}:
                self.thinking = False
                self.event = None
                self.ready_at = 0
            self.publish()
        self.table.cancel_ai()
        self.touch(sid)

    def rename(self, sid: str, name: str) -> None:
        """Rename only the caller's seat, preserving identity and current hand state."""
        name = player_name(name)
        if not name:
            raise ValueError('請輸入顯示名稱。')
        pid = self.touch(sid)
        self.table.check_recording()
        if name == self.names[sid]:
            return
        if self.started:
            self.names[sid] = name
            self.table.record_seat(pid, {
                'player_id': self.record_ids[sid], 'name': name, 'human': True,
            })
        self.names[sid] = name
        if not self.thinking:
            self.event = None  # A name change must not replay the previous discard animation.
        self.publish()

    def touch(self, sid: str) -> int:
        """Renew a member's reconnect grace and return the authoritative seat."""
        if sid not in self.seats:
            raise ValueError('你尚未加入這個房間。')
        if time.monotonic() - self.seen.get(sid, 0) >= self.RECONNECT_SECONDS:
            self.table.cancel_ai()
        self.last_active = self.seen[sid] = time.monotonic()
        return self.seats.index(sid)

    def snapshot(self, sid: str) -> dict:
        """Rotate only player indices, so every browser keeps its own seat at zero."""
        viewer = self.seats.index(sid)
        state = self.table.snapshot(viewer)
        state = relative_snapshot(state, viewer)
        state.pop('ai_pending', None)  # Unresolved reaction progress is private.
        relative = lambda pid: None if pid is None else (pid - viewer) % 4
        order = [(viewer + i) % 4 for i in range(4)]
        now = time.monotonic()
        state['room'] = {
            'code': self.code, 'started': self.started, 'host': sid == self.owner,
            'members': [
                {'name': (self.names[self.seats[pid]] if self.seats[pid] else
                          ['電腦玩家', '陳予安', '林小滿', '周子墨'][pid]),
                 'human': self.seats[pid] is not None,
                 'bot_controlled': (self.seats[pid] is None or
                                    now - self.seen.get(self.seats[pid], 0)
                                    >= self.RECONNECT_SECONDS),
                 'connected': (self.seats[pid] is not None and
                               now - self.seen.get(self.seats[pid], 0) < 30)}
                for pid in order
            ],
        }
        state['ai_editable'] = sid == self.owner
        state['waiting'] = not self.started
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

    def set_ai_levels(self, sid: str, levels: list[str]) -> None:
        """Host writes relative-seat settings; all members can inspect them."""
        viewer = self.touch(sid)
        if sid != self.owner:
            raise ValueError('只有房主能調整 AI 強度。')
        if (not isinstance(levels, list) or len(levels) != 4 or
                any(level not in ('standard', 'advanced') for level in levels)):
            raise ValueError('請為四個座位選擇標準或進階 AI。')
        absolute = [levels[(pid - viewer) % 4] for pid in range(4)]
        if self.started:
            self.table.set_ai_levels(absolute)
        else:
            self.table.ai_levels = absolute
        self.publish()

    def start(self, sid: str, next_hand: bool = False) -> None:
        """Let the host deal, or advance after the current hand has settled."""
        self.touch(sid)
        if sid != self.owner:
            raise ValueError('請由房主開局。')
        self.table.check_recording()
        if next_hand:
            if not self.started or not self.table.env.done:
                raise ValueError('本局尚未結束。')
            self.table.next_hand()
        elif self.started:
            raise ValueError('本桌已開局。')
        else:
            for pid in range(4):
                self.record_seat(pid)
            self.table.new_table(activate_recording=True, reset_ai=False)
        self.started = True
        self.event = None
        self.thinking = False
        self.ready_at = time.monotonic() + .5
        self.publish()

    def act(self, sid: str, version: int, request_id: str, action: dict) -> None:
        """Apply a legal current-seat action once; acknowledge already accepted retries."""
        pid = self.touch(sid)
        self.table.check_recording()
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
            raise ValueError('無效操作編號。')
        request_key = (self.record_ids[sid], request_id)
        if request_key in self.requests:
            return  # Retries acknowledge the original move without applying it twice.
        if (not self.started or self.table.env.done or version != self.version or
                time.monotonic() < self.ready_at or
                (self.table.env.phase != 'REACTION' and self.table.actor() != pid) or
                action not in self.table.env.legal_actions(pid)):
            raise ValueError('牌局已更新，請重新選擇操作。')
        self.table.request_id = request_id
        try:
            self.apply(action, pid=pid)
        finally:
            self.table.request_id = None
        self.requests[request_key] = self.version
        if len(self.requests) > 256:
            self.requests.pop(next(iter(self.requests)))

    def apply(self, action: dict, pid: int | None = None, *, source: str = 'human') -> None:
        """Apply a validated move, settle forced passes and publish its resolved event."""
        collecting = self.table.env.phase == 'REACTION'
        pid = self.table.actor() if pid is None else pid
        frames = []
        try:
            self.table.apply(action, frames, pid=pid, source=source)
            self.table.request_id = None
            # Automatic ting discards run in tick, preserving the shared action delay.
            self.table.advance(frames, auto_discard_ting=False)
        except RecordingError:
            self.publish()
            raise
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
        if (self.table.recording_error or not self.started or self.table.env.done
                or now < self.ready_at):
            return
        if self.ready_at and not self.thinking:
            self.ready_at = 0
            self.event = None
            self.publish()
        pid = self.table.actor()
        ting_discard = self.table.ting_discard()
        if ting_discard is not None:
            self.apply(ting_discard, pid=pid, source='auto_ting')
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
        action = self.table.choose_bot(pid)
        if action is not None:
            self.apply(action, pid=pid, source='bot')


class RoomRegistry:
    """Bounded in-memory rooms; one scheduler services all tables."""

    def __init__(self) -> None:
        self.rooms: dict[str, WebRoom] = {}
        self.memberships: dict[str, str] = {}
        self.lock = threading.Lock()

    def create(self, sid: str, table_factory: Callable[..., WebTable],
               name: str = '', *, player_id: str | None = None) -> WebRoom:
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
            room = WebRoom(code, sid, table_factory(human_pids={0, 1, 2, 3}), name,
                           player_id=player_id)
            self.rooms[code] = room
            self.memberships[sid] = code
            return room

    def join(self, sid: str, code: str, name: str = '', *,
             player_id: str | None = None) -> WebRoom:
        """Join a free seat without assigning one identity to multiple rooms."""
        with self.lock:
            room = self.rooms.get(code)
            if room is None:
                raise ValueError('找不到房間，可能已結束。')
            if sid in self.memberships and self.memberships[sid] != code:
                raise ValueError('請先離開目前房間。')
            with room.changed:
                room.join(sid, name, player_id=player_id)
            self.memberships[sid] = code
            return room

    def get(self, sid: str) -> WebRoom:
        """Return a member's room without accepting a client-supplied seat identity."""
        with self.lock:
            room = self.rooms.get(self.memberships.get(sid))
            if room is None:
                raise ValueError('你尚未加入房間，或房間已結束。')
            return room

    def recover(self, sid: str, player_id: str, document: dict,
                restore: Callable[[dict], WebTable], *, store: HandStore) -> WebRoom:
        """Reload the committed head under the room lock before replacing a failed table."""
        from app.web_records import can_resume

        code = document['metadata']['recovery']['room']['code']
        with self.lock:
            room = self.rooms.get(code)
            with room.changed if room is not None else nullcontext():
                # The routing document may predate another committed move or seat change.
                records = store.player_records(player_id, hand_id=document['hand_id'])
                if not records or not can_resume(records[0], store, player_id):
                    raise ValueError('此牌桌已有更新進度，請重新開啟紀錄。')
                document = records[0]
                saved = document['metadata']['recovery']['room']
                if sid in self.memberships and self.memberships[sid] != saved['code']:
                    raise ValueError('請先離開目前房間。')
                if room is not None and room.table.table_id != document['metadata']['table_id']:
                    raise ValueError('房號已使用，無法恢復這個牌桌。')
                if room is None or room.table.recording_error:
                    if len(self.rooms) >= 100:
                        raise ValueError('目前房間已滿，請稍後再試。')
                    if player_id not in saved['seats']:
                        raise ValueError('這個座位已經讓出，無法續局。')
                    if room is not None:
                        room.table.cancel_ai()
                    table = restore(document)
                    owner = 'reserved:' + (saved['owner'] or player_id)
                    room = WebRoom(saved['code'], owner, table)
                    room.seats = ['reserved:' + player if player else None
                                  for player in saved['seats']]
                    room.names = {member: saved['names'][pid]
                                  for pid, member in enumerate(room.seats) if member}
                    room.record_ids = {member: saved['seats'][pid]
                                       for pid, member in enumerate(room.seats) if member}
                    room.seen = {member: time.monotonic() for member in room.names}
                    room.started = True
                    room.version = saved['version'] + 1
                    room.requests = {
                        tuple(key): room.version for key in saved.get('requests', [])}
                    room.requests.update({
                        (decision['player_id'], decision['request_id']): room.version
                        for decision in document['metadata']['decisions']
                        if decision.get('request_id') and decision.get('player_id')})
                    self.rooms[room.code] = room
                with room.changed:
                    room.join(sid, player_id=player_id)
                self.memberships[sid] = room.code
                return room

    def leave(self, sid: str) -> None:
        """Vacate a seat for a bot and transfer host ownership if needed."""
        with self.lock:
            room = self.rooms.get(self.memberships.pop(sid, None))
            if room:
                with room.changed:
                    pid = room.seats.index(sid)
                    room.table.cancel_ai()
                    room.seats[pid] = None
                    room.seen.pop(sid, None)
                    room.names.pop(sid, None)
                    if room.owner == sid:
                        room.owner = next((s for s in room.seats if s), '')
                    room.publish()
                    room.record_seat(pid)

    def run(self, stop: threading.Event) -> None:
        """Schedule bot turns and expire empty or idle rooms until shutdown."""
        # ponytail: single-process rooms; use a shared store before adding server replicas.
        while not stop.wait(.1):
            now = time.monotonic()
            with self.lock:
                for code, room in list(self.rooms.items()):
                    if stop.is_set():
                        break
                    with room.changed:
                        if now - room.last_active > 3600 or not any(room.seats):
                            try:
                                room.table.interrupt_recording('room_expired')
                            except RecordingError:
                                pass  # The durable prefix remains active until restart recovery.
                            for sid in room.seats:
                                self.memberships.pop(sid, None)
                            del self.rooms[code]
                            continue
                        try:
                            room.tick(now)
                        except RecordingError:
                            pass  # Failed room already wakes clients; other rooms keep running.
