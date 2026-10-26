"""Prepare a loopback-only Pocket ID staging stack without production credentials."""

import argparse
import base64
import http.cookies
import json
import os
from pathlib import Path
import secrets
import subprocess
import urllib.request
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]


def public_origins(url: str) -> tuple[str, str]:
    """Keep Funnel's game on 443 and its separate identity origin on 8443."""
    origin = urlsplit(url)
    if (origin.scheme != 'https' or not origin.hostname
            or not origin.hostname.endswith('.ts.net') or origin.netloc != origin.hostname
            or origin.path or origin.query or origin.fragment
            or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for c in origin.hostname)):
        raise ValueError('Use the exact HTTPS ts.net origin without a path or port')
    return url, url + ':8443'


def private_directory(directory: Path) -> None:
    """Create a new owner-only directory, including SYSTEM for Windows Docker readers."""
    directory.mkdir(mode=0o700)
    if os.name == 'nt':
        # Restrict inheritance before writing secrets; SYSTEM is Docker Desktop's reader.
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


def initialize(directory: Path, table_port: int = 18080, identity_port: int = 18081,
               public_url: str | None = None) -> None:
    """Create restricted config; public HTTPS requires the separate Funnel overlay."""
    if not all(1024 <= port <= 65535 for port in (table_port, identity_port)):
        raise ValueError('Staging ports must be between 1024 and 65535')
    if table_port == identity_port:
        raise ValueError('Staging ports must be different')
    directory = directory.resolve()
    if directory == ROOT or ROOT in directory.parents:
        raise ValueError('Private configuration must be outside the repository')
    table = f'http://localhost:{table_port}'
    identity = f'http://localhost:{identity_port}'
    if public_url:
        table, identity = public_origins(public_url)
    private_directory(directory)
    backend_password = secrets.token_urlsafe(32)
    authorization = base64.b64encode(f'friend:{backend_password}'.encode()).decode()
    client_secret = secrets.token_urlsafe(32)
    proxy = {
        'provider': 'oidc', 'provider_display_name': '青禾麻將',
        'client_id': 'mahjong16-stage', 'client_secret': client_secret,
        'redirect_url': table + '/oauth2/callback',
        'oidc_issuer_url': identity, 'skip_oidc_discovery': True,
        'login_url': identity + '/authorize',
        'redeem_url': 'http://identity:1411/api/oidc/token',
        'oidc_jwks_url': 'http://identity:1411/.well-known/jwks.json',
        'profile_url': 'http://identity:1411/api/oidc/userinfo',
        # Identify users by sub so friends need not provide an email address.
        'scope': 'openid profile offline_access', 'oidc_email_claim': 'sub', 'email_domains': ['*'],
        'code_challenge_method': 'S256', 'http_address': '0.0.0.0:4180',
        'upstreams': ['static://202'], 'reverse_proxy': True,
        'skip_provider_button': True, 'set_xauthrequest': True,
        'pass_access_token': True,
        'session_store_type': 'redis', 'redis_connection_url': 'redis://sessions:6379/0',
        'cookie_name': '__Host-qinghe_session' if public_url else 'mahjong_stage_session',
        'cookie_secret': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'cookie_secure': bool(public_url), 'cookie_httponly': True, 'cookie_samesite': 'lax',
        'cookie_expire': '12h', 'cookie_refresh': '1s',
        'cookie_csrf_per_request': True, 'cookie_csrf_per_request_limit': 5,
        'request_logging': False, 'auth_logging': False,
    }
    files = {
        'stage.env': f'MAHJONG_STAGE_TABLE_PORT={table_port}\n'
                     f'MAHJONG_STAGE_IDENTITY_PORT={identity_port}\n'
                     f'MAHJONG_IDENTITY_ISSUER={identity}\n',
        'gateway.env': f'MAHJONG_BACKEND_AUTHORIZATION=Basic {authorization}\n' + (
            f'MAHJONG_POCKET_HOST={urlsplit(table).hostname}\n' if public_url else ''),
        'backend-password.txt': backend_password,
        'encryption-key.txt': secrets.token_urlsafe(32),
        'pocket.env': f'APP_URL={identity}\n',
        'proxy.cfg': '\n'.join(f'{key} = {json.dumps(value, ensure_ascii=False)}'
                               for key, value in proxy.items()) + '\n',
        'client.json': json.dumps({
            'id': 'mahjong16-stage',
            'name': '青禾麻將' if public_url else '青禾麻將測試',
            'callbackURLs': [table + '/oauth2/callback'],
            'isPublic': False, 'pkceEnabled': True, 'skipConsent': False,
        }),
        'client-secret.txt': client_secret,
    }
    for name, value in files.items():
        with (directory / name).open('x', encoding='utf-8') as handle:
            os.chmod(handle.name, 0o600)
            handle.write(value)
    print('Private staging configuration created; no production service was changed.')


def bootstrap(directory: Path, public_url: str | None = None,
              bootstrap_port: int | None = None) -> None:
    """Bootstrap through loopback before enabling a public Funnel listener."""
    directory = directory.resolve()
    identity = (directory / 'pocket.env').read_text(encoding='utf-8').strip().removeprefix('APP_URL=')
    # Never send the bootstrap session or client secret to an arbitrary host.
    origin = urlsplit(identity)
    endpoint = identity
    headers = {}
    if public_url:
        if identity != public_origins(public_url)[1]:
            raise ValueError('Configured identity origin does not match the approved URL')
        if bootstrap_port is None or not 1024 <= bootstrap_port <= 65535:
            raise ValueError('Public bootstrap requires a loopback listener port')
        endpoint = f'http://localhost:{bootstrap_port}'
        headers['Host'] = origin.netloc
    elif (origin.scheme != 'http' or origin.hostname != 'localhost'
            or origin.username or origin.password or origin.path
            or origin.query or origin.fragment):
        raise ValueError('Bootstrap is restricted to the localhost staging identity service')
    cookie = ''

    def post(path: str, body: dict) -> dict:
        nonlocal cookie
        request = urllib.request.Request(endpoint + path, json.dumps(body).encode(),
                                         {'Content-Type': 'application/json', 'Origin': identity,
                                          'Cookie': cookie, **headers})
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.headers.get('Set-Cookie'):
                cookies = http.cookies.SimpleCookie(response.headers['Set-Cookie'])
                cookie = '; '.join(f'{key}={value.value}' for key, value in cookies.items())
            return json.load(response)

    client = json.loads((directory / 'client.json').read_text(encoding='utf-8'))
    client_secret = (directory / 'client-secret.txt').read_text(encoding='utf-8')
    # Validate local inputs before creating the administrator; never reset an existing account.
    post('/api/signup/setup', {'username': 'owner', 'firstName': '牌桌管理員'})
    post('/api/oidc/clients', client)
    post('/api/oidc/clients/mahjong16-stage/secrets', {
        'secret': client_secret})
    print('Staging owner and OIDC client created. Use a one-time login code to add your passkey.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--table-port', type=int, default=18080)
    parser.add_argument('--identity-port', type=int, default=18081)
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('--url', help='Approved public HTTPS ts.net game origin')
    parser.add_argument('--bootstrap-port', type=int, help='Loopback identity port before cutover')
    args = parser.parse_args()
    if args.bootstrap:
        bootstrap(args.output, args.url, args.bootstrap_port)
    else:
        initialize(args.output, args.table_port, args.identity_port, args.url)
