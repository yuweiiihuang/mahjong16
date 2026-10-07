"""Single-server SQLite persistence for private, replayable hand records."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import TYPE_CHECKING

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


def write_private_record(path: Path, document: dict) -> None:
    """Create an owner-only JSON record without overwriting existing files."""
    target = private_record_path(path)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
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
                self.connection.execute('PRAGMA user_version=1')
                self.connection.execute(
                    "UPDATE hands SET status='interrupted', reason='server_restart' "
                    "WHERE status='active'")
        except Exception:
            if hasattr(self, 'connection'):
                self.connection.close()
            self.owner.close()
            raise

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

    def __init__(self, store: HandStore, metadata: dict) -> None:
        super().__init__()
        self.store = store
        self.metadata = metadata
        self.step_context: dict = {}
        self.failure = False

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
            self.store.save(self.document(), self.metadata)
        except (sqlite3.Error, OSError) as error:
            self.failure = True
            raise RecordingError('牌譜保存失敗，本桌已暫停；請聯絡管理者。') from error
