"""Exercise an isolated gateway stack; no Funnel or production volumes are touched."""

import argparse
import importlib.util
import base64
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
AUTH_IMAGE = 'authelia/authelia:4.39@sha256:bd97cff4fcbf715b5ff1f9ae286afbe6033afce385302520b0368122d43a6f54'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--funnel', action='store_true', help='Test the Funnel HTTP listener')
    args = parser.parse_args()
    project = 'mahjong-gateway-qa-' + secrets.token_hex(4)
    host = 'gateway.mahjong.test'
    origin = f'https://{host}' + ('' if args.funnel else ':8443')
    spec = importlib.util.spec_from_file_location('configuration', ROOT / 'deploy/gateway/configure.py')
    configuration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(configuration)
    password = secrets.token_urlsafe(32)
    backend_password = secrets.token_urlsafe(32)
    authorization = 'Basic ' + base64.b64encode(
        f'friend:{backend_password}'.encode()).decode()
    fixture_root = 'C:/ProgramData/Qinghe' if os.name == 'nt' else None
    with tempfile.TemporaryDirectory(prefix='mahjong-gateway-qa-', dir=fixture_root) as directory:
        private = Path(directory)
        if os.name == 'nt':
            # Inherit the already restricted Qinghe ACL, including Docker's SYSTEM service.
            subprocess.run(['icacls.exe', str(private), '/reset'], check=True,
                           stdout=subprocess.DEVNULL)
        digest = subprocess.check_output([
            'docker', 'run', '--rm', '--network', 'none', AUTH_IMAGE,
            'authelia', 'crypto', 'hash', 'generate', 'argon2', '--password', password,
        ], encoding='utf-8').strip().removeprefix('Digest: ')
        config = configuration.auth_configuration(origin)
        users = {'users': {'qa': {'displayname': 'Gateway QA', 'password': digest,
                                 'email': 'qa@example.invalid', 'groups': ['players']}}}
        users['users']['outsider'] = {'displayname': 'Outsider', 'password': digest,
                                     'email': 'outsider@example.invalid', 'groups': []}
        users['users']['blocked'] = {'displayname': 'Blocked', 'password': digest,
                                    'email': 'blocked@example.invalid', 'groups': ['players']}
        for name, value in [('configuration.yml', config), ('users.yml', users)]:
            path = private / name
            path.write_text(json.dumps(value), encoding='utf-8')
            path.chmod(0o600)
        (private / 'backend-password.txt').write_text(backend_password, encoding='utf-8')
        (private / 'gateway.env').write_text(
            f'MAHJONG_BACKEND_AUTHORIZATION={authorization}\n', encoding='utf-8')
        for path in private.iterdir():
            path.chmod(0o600)
        env = {**os.environ, 'MAHJONG_GATEWAY_HOST': host,
               'MAHJONG_GATEWAY_CONFIG': str(private), 'MAHJONG_GATEWAY_PORT': '0'}
        compose = ['docker', 'compose', '-p', project, '-f',
                   str(ROOT / 'deploy/gateway/compose.yaml')]
        if args.funnel:
            compose += ['-f', str(ROOT / 'deploy/gateway/funnel.yaml')]

        def command(*args: str) -> str:
            return subprocess.check_output([*compose, *args], env=env, encoding='utf-8')

        try:
            command('up', '-d', '--pull', 'never')
            port = int(command('port', 'gateway', '8080' if args.funnel else '8443').strip().rsplit(':', 1)[1])
            # Only this ephemeral test listener uses a private, untrusted TLS certificate.
            context = ssl._create_unverified_context()

            def request(path: str, *, body: dict | None = None,
                        headers: dict | None = None) -> tuple[int, dict, bytes]:
                if args.funnel:
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                else:
                    connection = http.client.HTTPSConnection(host, port, context=context, timeout=5)
                    connection.sock = context.wrap_socket(
                        socket.create_connection(('127.0.0.1', port), timeout=5),
                        server_hostname=host)
                outgoing = {'Host': host if args.funnel else f'{host}:8443', **(headers or {})}
                payload = None
                if body is not None:
                    payload = json.dumps(body)
                    outgoing['Content-Type'] = 'application/json'
                    outgoing['Origin'] = origin
                try:
                    connection.request('POST' if body is not None else 'GET',
                                       path, payload, outgoing)
                    response = connection.getresponse()
                    return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
                finally:
                    connection.close()

            for attempt in range(30):
                try:
                    if request('/auth/')[0] == 200:
                        break
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(1)
            else:
                raise AssertionError('Auth portal did not become ready')

            web = command('ps', '-q', 'web').strip()
            auth = command('ps', '-q', 'auth').strip()
            for container in [web, auth]:
                bindings = subprocess.check_output([
                    'docker', 'inspect', container, '--format',
                    '{{json .NetworkSettings.Ports}}'], encoding='utf-8')
                assert not any(json.loads(bindings).values()), 'Private service has a host port'

            probe = '/api/state?gateway_probe=' + secrets.token_hex(8)
            for headers in [{}, {'Remote-User': 'qa', 'Remote-Groups': 'players',
                                 'Authorization': authorization,
                                 'X-Forwarded-User': 'qa',
                                 'X-Forwarded-For': '127.0.0.1',
                                 'X-Forwarded-Uri': '/', 'X-Forwarded-Proto': 'https'}]:
                status, _, _ = request(probe, headers=headers)
                assert status in (302, 303, 401, 403), status
            assert probe not in command('logs', '--no-color', 'web')
            print('PASS: anonymous and forged-header requests never reach the backend')

            status, headers, _ = request('/auth/api/firstfactor', body={
                'username': 'outsider', 'password': password, 'keepMeLoggedIn': False,
                'targetURL': origin + '/'})
            assert status == 200, status
            outsider_cookie = headers.get('set-cookie', '').split(';', 1)[0]
            status, _, _ = request(probe, headers={'Cookie': outsider_cookie})
            assert status == 403, status
            assert probe not in command('logs', '--no-color', 'web')
            for attempt in range(3):
                status, _, _ = request('/auth/api/firstfactor', body={
                    'username': 'blocked', 'password': 'incorrect', 'keepMeLoggedIn': False})
                assert status == 401, status
            status, _, _ = request('/auth/api/firstfactor', body={
                'username': 'blocked', 'password': password, 'keepMeLoggedIn': False})
            assert status == 401, 'A banned account could log in with the correct password'
            print('PASS: unapproved users are denied and repeated wrong passwords ban the account')

            status, _, _ = request('/auth/api/firstfactor', body={
                'username': 'qa', 'password': 'incorrect', 'keepMeLoggedIn': True,
                'targetURL': origin + '/'})
            assert status == 401, status
            status, headers, _ = request('/auth/api/firstfactor', body={
                'username': 'qa', 'password': password, 'keepMeLoggedIn': True,
                'targetURL': origin + '/'})
            assert status == 200, status
            cookie_header = headers.get('set-cookie', '')
            assert 'httponly' in cookie_header.lower() and 'secure' in cookie_header.lower(), (
                list(headers), cookie_header.split(';')[1:])
            assert 'max-age=' in cookie_header.lower() or 'expires=' in cookie_header.lower()
            cookie = cookie_header.split(';', 1)[0]
            status, _, page = request('/', headers={'Cookie': cookie})
            assert status == 200 and b'/access/login' not in page
            status, _, _ = request('/table3d.js', headers={'Cookie': cookie})
            assert status == 200
            print('PASS: login, remembered secure cookie, and game assets work without a second login')

            status, headers, body = request('/api/rooms', body={'name': 'Gateway QA'},
                                            headers={'Cookie': cookie})
            assert status == 200 and json.loads(body)['room']['host']
            identity = headers.get('set-cookie', '').split(';', 1)[0]
            if identity:
                cookie += '; ' + identity
            status, _, body = request('/api/room/start', body={}, headers={'Cookie': cookie})
            assert status == 200 and json.loads(body)['room']['started']
            status, _, _ = request('/api/room/leave', body={}, headers={'Cookie': cookie})
            assert status == 200
            print('PASS: protected game API supports room creation, starting, and leaving')

            command('stop', 'auth')
            status, _, _ = request(probe, headers={'Cookie': cookie})
            assert status in (502, 503), status
            assert probe not in command('logs', '--no-color', 'web')
            print('PASS: auth-service failure blocks access instead of bypassing verification')
        except Exception:
            print(command('logs', '--no-color', '--tail', '15', 'auth', 'gateway'))
            raise
        finally:
            # This unique project contains only disposable QA volumes.
            subprocess.run([*compose, 'down', '-v'], env=env, check=True,
                           stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
