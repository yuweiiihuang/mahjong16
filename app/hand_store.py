"""Single-server SQLite persistence for private, replayable hand records."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing, contextmanager
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import threading
import tempfile
from typing import TYPE_CHECKING, Callable, Iterator, TextIO
from uuid import uuid4

from domain.gameplay.recording import HandRecorder

if TYPE_CHECKING:
    from domain.gameplay.game_env import MahjongEnvironment


class RecordingError(RuntimeError):
    """A table must stop when an accepted state cannot be saved durably."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def private_record_path(path: Path) -> Path:
    """Reject private artifacts inside the public static-file directory."""
    target = path.expanduser().resolve()
    web_root = Path(__file__).resolve().parents[1] / 'ui' / 'web'
    if target.is_relative_to(web_root.resolve()):
        raise ValueError('私有牌譜不能放在網站公開目錄。')
    return target


@contextmanager
def open_private_record(path: Path) -> Iterator[TextIO]:
    """Publish a complete owner-only output atomically, without replacing existing files."""
    target = private_record_path(path)
    if target.exists():
        raise FileExistsError(f'輸出檔案已存在：{target}')
    descriptor, temporary = tempfile.mkstemp(
        prefix=f'.{target.name}.', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        # A same-directory hard link publishes without clobbering a concurrent output.
        os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_private_record(path: Path, document: dict) -> None:
    """Write a private JSON hand record."""
    with open_private_record(path) as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)


class HandStore:
    """One writer per database; serialize transactions across HTTP and bot threads."""

    def __init__(self, path: Path) -> None:
        self.path = private_record_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.Lock()
        self.closed = False
        self.owner = (self.path.parent / (self.path.name + '.lock')).open('a+b')
        self.owner.seek(0)
        if not self.owner.read(1):
            self.owner.write(b'0')
            self.owner.flush()
        self.owner.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.owner.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.connection = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
            self.path.chmod(0o600)
            with self.connection:
                version = self.connection.execute('PRAGMA user_version').fetchone()[0]
                if version not in (0, 1):
                    raise ValueError('不支援的牌譜資料庫版本。')
                self.connection.execute('''CREATE TABLE IF NOT EXISTS hands (
                    hand_id TEXT PRIMARY KEY, table_id TEXT NOT NULL,
                    started_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT, document TEXT NOT NULL)''')
                self.connection.execute('''CREATE TABLE IF NOT EXISTS account_players (
                    issuer TEXT NOT NULL, subject TEXT NOT NULL, player_id TEXT NOT NULL UNIQUE,
                    PRIMARY KEY (issuer, subject))''')
                self.connection.execute('''CREATE TABLE IF NOT EXISTS browser_players (
                    cookie_hash TEXT PRIMARY KEY, player_id TEXT NOT NULL UNIQUE)''')
                self.connection.execute('''CREATE TABLE IF NOT EXISTS practice_selection (
                    player_id TEXT PRIMARY KEY, table_id TEXT NOT NULL)''')
                self.connection.execute('''CREATE INDEX IF NOT EXISTS hands_started
                    ON hands(started_at DESC)''')
                self.connection.execute('''CREATE INDEX IF NOT EXISTS hands_table_started
                    ON hands(table_id, started_at DESC)''')
                self.connection.execute('PRAGMA user_version=1')
                self.connection.execute(
                    "UPDATE hands SET status='interrupted', reason='server_restart' "
                    "WHERE status='active'")
        except Exception:
            if hasattr(self, 'connection'):
                self.connection.close()
            self.owner.close()
            raise

    def account_player_id(self, issuer: str, subject: str) -> str:
        """Map a verified provider subject to a private ID, independent of names and devices."""
        with self.lock, self.connection:
            self.connection.execute(
                'INSERT OR IGNORE INTO account_players VALUES (?, ?, ?)',
                (issuer, subject, str(uuid4())))
            return self.connection.execute(
                'SELECT player_id FROM account_players WHERE issuer=? AND subject=?',
                (issuer, subject)).fetchone()[0]

    def browser_player_id(self, cookie: str, *, create: bool = False) -> str | None:
        """Recognize an anonymous browser after restart, without storing its credential."""
        digest = hashlib.sha256(cookie.encode()).hexdigest()
        with self.lock, self.connection:
            if create:
                self.connection.execute('INSERT OR IGNORE INTO browser_players VALUES (?, ?)',
                                        (digest, str(uuid4())))
            row = self.connection.execute(
                'SELECT player_id FROM browser_players WHERE cookie_hash=?', (digest,)).fetchone()
        return row[0] if row else None

    def player_records(self, player_id: str, *, hand_id: str | None = None) -> list[dict]:
        """Materialize authorized records before replay; never retain a live read cursor."""
        query = '''SELECT document, status, reason FROM hands
            WHERE (EXISTS (SELECT 1 FROM json_each(json_extract(document, '$.metadata.players'))
                          WHERE json_extract(value, '$.player_id')=?)
               OR EXISTS (SELECT 1 FROM json_each(json_extract(document, '$.metadata.seat_events'))
                          WHERE json_extract(value, '$.player_id')=?))'''
        parameters = [player_id, player_id]
        if hand_id is not None:
            query += ' AND hand_id=?'
            parameters.append(hand_id)
        query += ' ORDER BY started_at DESC LIMIT 100'
        with self.lock:
            rows = self.connection.execute(query, parameters).fetchall()
        records = [{**json.loads(raw), 'storage_status': status, 'interruption_reason': reason}
                   for raw, status, reason in rows]
        records.sort(key=lambda record: record['metadata']['started_at'], reverse=True)
        if hand_id is not None:
            records = [record for record in records if record['hand_id'] == hand_id]
        return records

    def latest_hand_id(self, table_id: str) -> str | None:
        """Only the latest committed hand of a table can be continued."""
        with self.lock:
            row = self.connection.execute(
                'SELECT hand_id FROM hands WHERE table_id=? '
                'ORDER BY started_at DESC, rowid DESC LIMIT 1',
                (table_id,)).fetchone()
        return row[0] if row else None

    def practice_hands(self, player_id: str, *, table_id: str | None = None,
                       heads: bool = False) -> list[dict]:
        """Read owned practice summaries without private walls, steps or a 100-hand cutoff."""
        query = '''SELECT h.hand_id, h.table_id, h.started_at,
            json_extract(h.document, '$.metadata.hand_index') AS round,
            json_extract(h.document, '$.status') AS status,
            json_extract(h.document, '$.engine_version') AS engine_version,
            json_extract(h.document, '$.metadata.recovery.version') AS recovery_version,
            h.reason,
            json_extract(h.document, '$.metadata.players') AS players,
            json_extract(h.document, '$.metadata.totals_before') AS totals_before,
            json_extract(h.document, '$.metadata.totals_after') AS totals_after,
            json_extract(h.document, '$.settlement') AS result,
            json_extract(h.document, '$.metadata.settlement.payer') AS payer,
            json_extract(h.document, '$.setup.quan_feng') AS quan_feng,
            json_extract(h.document, '$.setup.dealer_pid') AS dealer,
            (SELECT MIN(started_at) FROM hands WHERE table_id=h.table_id) AS session_started,
            (SELECT COUNT(*) FROM hands WHERE table_id=h.table_id
                AND status='completed') AS completed_hands
            FROM hands h WHERE json_extract(h.document, '$.metadata.source')='practice'
            AND json_extract(h.document, '$.metadata.players[0].player_id')=?'''
        parameters = [player_id]
        if table_id is not None:
            query += ' AND h.table_id=?'
            parameters.append(table_id)
        if heads:
            query += ''' AND NOT EXISTS (SELECT 1 FROM hands newer
                WHERE newer.table_id=h.table_id AND
                (newer.started_at>h.started_at OR
                 (newer.started_at=h.started_at AND newer.rowid>h.rowid)))'''
        query += ' ORDER BY h.started_at, h.rowid'
        with self.lock:
            cursor = self.connection.execute(query, parameters)
            keys = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            cursor.close()
        items = [dict(zip(keys, row)) for row in rows]
        for item in items:
            for key in ('players', 'totals_before', 'totals_after', 'result'):
                item[key] = json.loads(item[key]) if item[key] is not None else None
        return items

    def selected_practice(self, player_id: str) -> str | None:
        """Remember the selected game independently of a browser connection's lifetime."""
        with self.lock:
            row = self.connection.execute(
                'SELECT table_id FROM practice_selection WHERE player_id=?',
                (player_id,)).fetchone()
        return row[0] if row else None

    def select_practice(self, player_id: str, table_id: str) -> None:
        """Persist selection only after a game has been saved or verified for this player."""
        with self.lock, self.connection:
            self.connection.execute('''INSERT INTO practice_selection VALUES (?, ?)
                ON CONFLICT(player_id) DO UPDATE SET table_id=excluded.table_id''',
                (player_id, table_id))

    def save(self, document: dict, metadata: dict) -> None:
        """Commit the full accepted prefix before acknowledging an operation.

        ponytail: rewrite one small hand JSON per step; split steps into rows if measured
        write latency or record size exceeds the needs of a single friends' server.
        """
        payload = json.dumps({**document, 'metadata': metadata}, ensure_ascii=False)
        status = 'completed' if document['status'] == 'completed' else 'active'
        with self.lock, self.connection:
            self.connection.execute('''INSERT INTO hands VALUES (?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(hand_id) DO UPDATE SET updated_at=excluded.updated_at,
                status=excluded.status, document=excluded.document''',
                (document['hand_id'], metadata['table_id'], metadata['started_at'],
                 _now(), status, payload))

    def interrupt(self, hand_id: str, reason: str) -> None:
        """Keep unfinished prefixes; do not treat interruptions as losses or draws."""
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE hands SET status='interrupted', reason=?, updated_at=? "
                "WHERE hand_id=? AND status='active'", (reason, _now(), hand_id))

    def backup(self, target: Path) -> None:
        """Make a consistent backup, never overwriting an existing destination."""
        with self.lock:
            _backup(self.connection, target)

    def close(self) -> None:
        """Release database and process ownership after all server threads have stopped."""
        with self.lock:
            if self.closed:
                return
            self.connection.close()
            self.owner.close()
            self.closed = True


def stored_hand(path: Path, hand_id: str) -> dict:
    """Read a private hand without claiming server ownership or altering its status."""
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        row = connection.execute(
            'SELECT document, status, reason FROM hands WHERE hand_id=?', (hand_id,)
        ).fetchone()
    if row is None:
        raise ValueError('找不到指定牌局。')
    return {**json.loads(row[0]), 'storage_status': row[1], 'interruption_reason': row[2]}


def stored_hands(path: Path) -> list[dict]:
    """List IDs and lifecycle status for offline administration, not a public API."""
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        rows = connection.execute(
            'SELECT hand_id, table_id, status, started_at FROM hands ORDER BY started_at'
        ).fetchall()
    return [dict(zip(('hand_id', 'table_id', 'status', 'started_at'), row)) for row in rows]


def _backup(connection: sqlite3.Connection, target: Path) -> None:
    target = private_record_path(target)
    with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb'):
        pass
    try:
        target.chmod(0o600)
        with closing(sqlite3.connect(target)) as destination:
            connection.backup(destination)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def backup_database(path: Path, target: Path) -> None:
    """Back up live or stopped databases without changing active hand status."""
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        _backup(connection, target)


class PersistentHandRecorder(HandRecorder):
    """Reuse engine recording, committing each initialized state and accepted step."""

    def __init__(self, store: HandStore, metadata: dict, *,
                 recovery: Callable[[], dict] | None = None) -> None:
        super().__init__()
        self.store = store
        self.metadata = metadata
        self.step_context: dict = {}
        self.failure = False
        self.recovery = recovery

    def begin(self, env: MahjongEnvironment) -> None:
        self.records.clear()  # Only the current hand stays in memory; SQLite retains old hands.
        super().begin(env)

    def initialized(self, env: MahjongEnvironment) -> None:
        super().initialized(env)
        if not env.done:
            self.persist()

    def after_step(self, env: MahjongEnvironment, step: dict, result: tuple) -> None:
        super().after_step(env, step, result)
        self.metadata['decisions'].append({
            'seq': step['seq'], 'at': _now(), **self.step_context,
        })
        # Terminal state and table totals are committed together by WebTable.settle().
        if not env.done:
            self.persist()

    def before_step(self, env: MahjongEnvironment, action: dict, pid: int | None) -> dict:
        if self.failure:
            raise RecordingError('牌譜保存失敗，本桌已暫停；請聯絡管理者。')
        return super().before_step(env, action, pid)

    def persist(self) -> None:
        """Fail closed: an in-memory move cannot be acknowledged after a failed commit."""
        if self.failure:
            raise RecordingError('牌譜保存失敗，本桌已暫停；請聯絡管理者。')
        try:
            if self.recovery is not None:
                self.metadata['recovery'] = self.recovery()
            self.store.save(self.document(), self.metadata)
        except (sqlite3.Error, OSError) as error:
            self.failure = True
            raise RecordingError('牌譜保存失敗，本桌已暫停；請聯絡管理者。') from error
