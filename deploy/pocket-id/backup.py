"""Back up the default Pocket ID SQLite data and private configuration without downtime."""

import argparse
from pathlib import Path
import sqlite3
import tempfile
import zipfile


CONFIG_FILES = ('stage.env', 'gateway.env', 'pocket.env', 'proxy.cfg', 'encryption-key.txt',
                'backend-password.txt', 'client.json', 'client-secret.txt')


def backup(data: Path, config: Path, output: Path) -> None:
    """Snapshot SQLite consistently; uploads are copied without a cross-file transaction."""
    files = [config / name for name in CONFIG_FILES]
    uploads = list((data / 'uploads').rglob('*'))
    if any(path.is_symlink() for path in [data, config, data / 'pocket-id.db',
                                         data / 'uploads', *files, *uploads]):
        raise ValueError('Backup inputs must not contain links')
    if not all(path.is_file() for path in files):
        raise ValueError('Private backup configuration is incomplete')
    if output.exists():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        snapshot = Path(directory) / 'pocket-id.db'
        source = sqlite3.connect((data / 'pocket-id.db').resolve().as_uri() + '?mode=ro',
                                 uri=True, timeout=5)
        destination = sqlite3.connect(snapshot)
        try:
            source.backup(destination)
            assert destination.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        finally:
            destination.close()
            source.close()
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, 'identity/pocket-id.db')
            for path in uploads:
                if path.is_file():
                    archive.write(path, 'identity/' + path.relative_to(data).as_posix())
            for path in files:
                archive.write(path, 'config/' + path.name)
        with zipfile.ZipFile(output) as archive:
            assert archive.testzip() is None
    print('Verified identity archive; encryption key included. Keep the archive private.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    backup(args.data, args.config, args.output)
