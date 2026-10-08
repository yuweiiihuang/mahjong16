"""Create private gateway configuration outside the repository; never overwrite secrets."""

import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from urllib.parse import urlsplit

AUTH_IMAGE = 'authelia/authelia:4.39@sha256:bd97cff4fcbf715b5ff1f9ae286afbe6033afce385302520b0368122d43a6f54'


def auth_configuration(url: str) -> dict:
    """Build deny-by-default authentication for one HTTPS origin."""
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in ('', '/') or parsed.query
            or parsed.fragment):
        raise ValueError('Expected an HTTPS origin without credentials, path or query')
    host = parsed.hostname
    if parsed.port == 0:
        raise ValueError('Expected an HTTPS port between 1 and 65535')
    if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', host):
        raise ValueError('Expected a DNS hostname')
    url = url.rstrip('/')
    return {
        'server': {'address': 'tcp://:9091/auth', 'disable_healthcheck': True},
        'log': {'level': 'info'},
        'authentication_backend': {
            'password_reset': {'disable': True},
            'file': {'path': '/config/users.yml'},
        },
        'access_control': {
            'default_policy': 'deny',
            'rules': [{'domain': host, 'policy': 'one_factor',
                       'subject': ['group:players']}],
        },
        'session': {
            'secret': secrets.token_hex(32), 'name': 'mahjong_gateway_session',
            'inactivity': '12h', 'expiration': '12h', 'remember_me': '7d',
            'cookies': [{'domain': host,
                         'authelia_url': url + '/auth/',
                         'default_redirection_url': url + '/'}],
        },
        'storage': {'encryption_key': secrets.token_hex(32),
                    'local': {'path': '/data/auth.sqlite3'}},
        'notifier': {'filesystem': {'filename': '/data/notifications.txt'}},
        'ntp': {'disable_startup_check': True},
        'regulation': {'max_retries': 3, 'find_time': '2m', 'ban_time': '5m'},
    }


def initialize(directory: Path, url: str, username: str) -> None:
    """Create a new restricted config directory and a random login without logging it."""
    config = auth_configuration(url)
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', username):
        raise ValueError('Username must be 1-32 lowercase letters, digits, underscores or hyphens')
    directory = directory.resolve()
    root = Path(__file__).resolve().parents[2]
    if directory == root or root in directory.parents:
        raise ValueError('Private configuration must be outside the repository')
    directory.mkdir(mode=0o700)  # Existing directories are never overwritten.
    if os.name == 'nt':
        # Explicit allowlist before creating any secrets; SYSTEM is Docker Desktop's reader.
        script = '''
$ErrorActionPreference = 'Stop'
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$system = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')
foreach ($identity in @($sid, $system)) {
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $env:MAHJONG_NEW_CONFIG -AclObject $acl
'''
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                       env={**os.environ, 'MAHJONG_NEW_CONFIG': str(directory)}, check=True,
                       stdout=subprocess.DEVNULL)
    result = subprocess.check_output([
        'docker', 'run', '--rm', '--network', 'none', AUTH_IMAGE,
        'authelia', 'crypto', 'hash', 'generate', 'argon2', '--random', '--random.length', '32',
    ], encoding='utf-8', timeout=60)
    fields = dict(line.split(': ', 1) for line in result.splitlines() if ': ' in line)
    password, digest = fields['Random Password'], fields['Digest']
    if not digest.startswith('$argon2id$') or len(password) < 32:
        raise ValueError('Unexpected password generator output')
    backend_password = secrets.token_urlsafe(32)
    authorization = base64.b64encode(f'friend:{backend_password}'.encode()).decode()
    users = {'users': {username: {'displayname': username, 'password': digest,
                                'email': username + '@example.invalid', 'groups': ['players']}}}
    files = {
        'configuration.yml': json.dumps(config),
        'users.yml': json.dumps(users),
        'gateway.env': f'MAHJONG_BACKEND_AUTHORIZATION=Basic {authorization}\n',
        'backend-password.txt': backend_password,
        'login.txt': f'{url}\nUsername: {username}\nPassword: {password}\n',
    }
    for name, value in files.items():
        with (directory / name).open('x', encoding='utf-8') as output:
            os.chmod(output.name, 0o600)
            output.write(value)
    print('Private configuration created. Read login.txt locally; do not commit it.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--user', required=True)
    args = parser.parse_args()
    initialize(args.output, args.url, args.user)
