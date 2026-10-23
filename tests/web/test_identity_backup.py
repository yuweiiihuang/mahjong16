"""The identity archive retains committed accounts and the exact encryption key."""

import importlib.util
from pathlib import Path
import sqlite3
import zipfile

import pytest


spec = importlib.util.spec_from_file_location(
    'pocket_backup', Path(__file__).resolve().parents[2] / 'deploy/pocket-id/backup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_online_archive_preserves_committed_sqlite_and_private_configuration(tmp_path):
    data, config = tmp_path / 'data', tmp_path / 'config'
    data.mkdir()
    config.mkdir()
    (data / 'uploads').mkdir()
    (data / 'uploads' / 'avatar.png').write_bytes(b'avatar')
    for name in module.CONFIG_FILES:
        (config / name).write_bytes(b'private-' + name.encode())
    connection = sqlite3.connect(data / 'pocket-id.db')
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('CREATE TABLE users (id TEXT PRIMARY KEY)')
    connection.execute("INSERT INTO users VALUES ('original-account')")
    connection.commit()
    try:
        output = tmp_path / 'identity.zip'
        module.backup(data, config, output)
        connection.execute("INSERT INTO users VALUES ('later-account')")
        connection.commit()
        with zipfile.ZipFile(output) as archive:
            assert archive.read('config/encryption-key.txt') == b'private-encryption-key.txt'
            assert archive.read('identity/uploads/avatar.png') == b'avatar'
            restored = tmp_path / 'restored.db'
            restored.write_bytes(archive.read('identity/pocket-id.db'))
        with sqlite3.connect(restored) as snapshot:
            assert snapshot.execute('SELECT id FROM users').fetchall() == [('original-account',)]
        with pytest.raises(FileExistsError):
            module.backup(data, config, output)
    finally:
        connection.close()


def test_incomplete_config_does_not_create_archive(tmp_path):
    with pytest.raises(ValueError, match='incomplete'):
        module.backup(tmp_path / 'data', tmp_path / 'config', tmp_path / 'identity.zip')
    assert not (tmp_path / 'identity.zip').exists()
