"""Test real invite/OIDC boundaries in disposable containers, never the public stack."""

import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[2]


def request(port: int, path: str, body: dict | None = None,
            headers: dict | None = None, method: str | None = None) -> tuple[int, dict, bytes]:
    """Make one loopback request without following redirects or logging credentials."""
    connection = http.client.HTTPConnection('localhost', port, timeout=10)
    outgoing = {'Origin': f'http://localhost:{port}', **(headers or {})}
    if body is not None:
        outgoing['Content-Type'] = 'application/json'
    try:
        connection.request(method or ('POST' if body is not None else 'GET'), path,
                           json.dumps(body) if body is not None else None, outgoing)
        response = connection.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        connection.close()


def main() -> None:
    if not os.environ.get('MAHJONG_IMAGE'):
        raise SystemExit('Set MAHJONG_IMAGE to the locally built staging game image')
    spec = importlib.util.spec_from_file_location(
        'pocket_config', ROOT / 'deploy/pocket-id/configure.py')
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    project = 'mahjong-pocket-qa-' + secrets.token_hex(4)
    # Keep both reservations until two distinct ephemeral ports have been assigned.
    with socket.socket() as first, socket.socket() as second:
        first.bind(('127.0.0.1', 0))
        second.bind(('127.0.0.1', 0))
        table_port, identity_port = first.getsockname()[1], second.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='mahjong-pocket-qa-') as directory:
        private = Path(directory) / 'private'
        config.initialize(private, table_port, identity_port)
        env = {**os.environ, 'MAHJONG_POCKET_CONFIG': str(private)}
        compose = ['docker', 'compose', '--env-file', str(private / 'stage.env'),
                   '-p', project, '-f', str(ROOT / 'deploy/pocket-id/compose.yaml')]
        projects = [compose]

        def command(*args: str) -> str:
            return subprocess.check_output([*compose, *args], env=env, encoding='utf-8',
                                           timeout=120, stderr=subprocess.PIPE)

        def identity(path: str, body: dict | None = None, cookie: str = '') -> tuple:
            return request(identity_port, path, body, {'Cookie': cookie})

        def cookie_from(headers: dict) -> str:
            return headers.get('set-cookie', '').split(';', 1)[0]

        def login_code(username: str) -> str:
            output = command('exec', '-T', 'identity', '/app/pocket-id',
                             'one-time-access-token', username)
            token = re.search(r'/lc/([^\s]+)', output).group(1)
            status, headers, _ = identity('/api/one-time-access-token/' + token, {})
            assert status == 200, ('one-time login', status)
            assert identity('/api/one-time-access-token/' + token, {})[0] >= 400
            return cookie_from(headers)

        def sign_in(cookie: str) -> str:
            status, headers, _ = request(table_port, '/oauth2/start?rd=/')
            assert status == 302, ('OIDC start', status)
            csrf = cookie_from(headers)
            authorization = urlsplit(headers['location'])
            assert authorization.netloc == f'localhost:{identity_port}'
            query = parse_qs(authorization.query)
            assert query['code_challenge_method'] == ['S256']
            status, headers, _ = identity(authorization.path + '?' + authorization.query,
                                          cookie=cookie)
            assert status in (302, 303), ('authorization', status)
            location = urlsplit(headers['location'])
            if location.path == '/interaction':
                interaction = parse_qs(location.query)['interaction'][0]
                status, _, payload = identity('/api/oidc/interactions/' + interaction,
                                              cookie=cookie)
                assert status == 200 and json.loads(payload)['currentStep'] == 'consent'
                status, _, payload = identity('/api/oidc/interactions/' + interaction + '/complete',
                                              {'step': 'consent'}, cookie)
                assert status == 200, ('consent', status)
                resume = urlsplit(json.loads(payload)['redirectUrl'])
                status, headers, _ = identity(resume.path + '?' + resume.query, cookie=cookie)
                assert status in (302, 303), ('authorization resume', status)
                location = urlsplit(headers['location'])
            assert location.netloc == f'localhost:{table_port}'
            callback = location.path + '?' + location.query
            # The actual code must not be accepted without its browser CSRF cookie.
            assert request(table_port, callback)[0] == 403
            status, headers, _ = request(table_port, callback, headers={'Cookie': csrf})
            assert status == 302, ('OIDC callback', status)
            return cookie_from(headers)

        try:
            command('up', '-d', '--pull', 'never')
            for _ in range(45):
                try:
                    if identity('/api/signup/setup')[0] == 204:
                        break
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(1)
            else:
                raise AssertionError('Staging identity service did not become ready')
            for service in ('identity', 'proxy', 'sessions', 'web'):
                bindings = subprocess.check_output([
                    'docker', 'inspect', command('ps', '-q', service).strip(),
                    '--format', '{{json .NetworkSettings.Ports}}'], encoding='utf-8')
                assert not any(json.loads(bindings).values()), (service, 'has a host port')
            probe = '/api/state?pocket_probe=' + secrets.token_hex(8)
            backend_auth = (private / 'gateway.env').read_text(encoding='utf-8').split('=', 1)[1].strip()
            forged = {'Remote-User': 'owner', 'X-Auth-Request-User': 'owner',
                      'X-Qinghe-Subject': 'owner',
                      'X-Forwarded-User': 'owner', 'X-Forwarded-For': '127.0.0.1',
                      'Authorization': backend_auth}
            for headers in ({}, forged):
                status = request(table_port, probe, headers=headers)[0]
                assert status == 302, ('anonymous access', status)
            assert probe not in command('logs', '--no-color', 'web')
            print('PASS: anonymous and forged credentials do not reach the private game')

            config.bootstrap(private)
            assert identity('/api/signup/setup', {'username': 'second-owner'})[0] >= 400
            admin = login_code('owner')
            status, _, payload = identity('/api/webauthn/register/start', cookie=admin)
            assert status == 200, ('first passkey registration options', status)
            registration = json.loads(payload)
            assert registration['rp']['id'] == 'localhost'
            assert registration['user']['name'] == 'owner' and registration['challenge']
            assert not registration.get('excludeCredentials')
            assert registration['authenticatorSelection']['userVerification'] == 'required'
            print('PASS: an account with no passkeys receives new-key registration options')
            assert identity('/api/signup', {'username': 'uninvited'})[0] >= 400

            def invite(ttl: str = '1h') -> dict:
                status, _, payload = identity('/api/signup-tokens',
                                              {'ttl': ttl, 'usageLimit': 1}, admin)
                assert status == 201, ('create invitation', status)
                return json.loads(payload)

            users = []
            for name in ('friend-one', 'friend-two'):
                token = invite()['token']
                status, headers, payload = identity('/api/signup', {
                    'username': name, 'firstName': '朋友', 'token': token})
                assert status == 201, ('invited signup', status)
                user = json.loads(payload)
                assert user['username'] == name and not user['isAdmin']
                users.append((user['id'], cookie_from(headers)))
                repeat = {'username': name + '-again', 'token': token}
                assert identity('/api/signup', repeat)[0] >= 400
            expired = invite('2s')['token']
            # Pocket ID rounds token creation to the nearest second, including upward.
            time.sleep(3)
            assert identity('/api/signup', {'username': 'expired', 'token': expired})[0] >= 400
            revoked = invite()
            status, _, _ = request(identity_port, '/api/signup-tokens/' + revoked['id'],
                                    headers={'Cookie': admin}, method='DELETE')
            assert status == 204
            assert identity('/api/signup', {'username': 'revoked',
                                            'token': revoked['token']})[0] >= 400
            assert users[0][0] != users[1][0]
            print('PASS: invites are required, single use, expiring and revocable')
            recovery = login_code('friend-one')
            status, _, payload = identity('/api/users/me', cookie=recovery)
            assert status == 200 and json.loads(payload)['id'] == users[0][0]
            print('PASS: one-time recovery retains the existing player identity')

            sessions = []
            for user_id, cookie in users:
                session = sign_in(cookie)
                assert session and 'mahjong_stage_session=' in session
                status, _, page = request(table_port, '/', headers={'Cookie': session})
                assert status == 200 and b'/access/login' not in page
                status, auth_headers, _ = request(table_port, '/oauth2/auth',
                                                   headers={'Cookie': session})
                assert status == 202 and 'x-auth-request-access-token' not in auth_headers
                status, _, info = request(table_port, '/oauth2/userinfo',
                                           headers={'Cookie': session})
                assert status == 200 and json.loads(info)['user'] == user_id
                sessions.append(session)
            assert sessions[0] != sessions[1]
            assert request(table_port, '/oauth2/callback?code=forged&state=forged')[0] >= 400
            print('PASS: real OIDC/PKCE, consent, CSRF protection and separate friend sessions')

            status, _, payload = request(table_port, '/api/rooms', {'name': '朋友一'},
                                          {'Cookie': sessions[0]})
            assert status == 200, ('account room creation', status)
            room_code = json.loads(payload)['room']['code']
            status, _, payload = request(table_port, '/api/state', headers={'Cookie': sessions[0]})
            assert status == 200 and json.loads(payload)['room']['code'] == room_code
            # A signed-in friend cannot replace their verified subject with a request header.
            status, _, _ = request(table_port, '/api/room/state', headers={
                'Cookie': sessions[1], 'X-Qinghe-Subject': users[0][0]})
            assert status == 400, ('forged subject took another account seat', status)
            status, _, _ = request(table_port, '/api/room/join',
                                   {'code': room_code, 'name': '朋友二', 'player_id': users[0][0]},
                                   {'Cookie': sessions[1]})
            assert status == 200
            assert request(table_port, '/api/room/start', {}, {'Cookie': sessions[0]})[0] == 200
            web = command('ps', '-q', 'web').strip()
            # Fetch and close a short-lived reader; never retain a cursor on the live database.
            records = json.loads(subprocess.check_output([
                'docker', 'exec', web, 'python', '-c',
                'import sqlite3,json; '
                'c=sqlite3.connect("file:/var/lib/mahjong16/hands.sqlite3?mode=ro",uri=True); '
                'rows=c.execute("SELECT document FROM hands").fetchall(); c.close(); '
                'print(json.dumps([json.loads(row[0])["metadata"]["players"] for row in rows]))',
            ], encoding='utf-8'))
            multiplayer = next(players for players in records if players[1]['human'])
            assert multiplayer[0]['player_id'] != multiplayer[1]['player_id']
            for user_id, _ in users:
                assert user_id not in json.dumps(records)
            print('PASS: trusted subjects own seats; records contain private stable IDs only')

            status, headers, _ = request(table_port, '/oauth2/sign_out',
                                         headers={'Cookie': sessions[0]})
            assert status in (200, 302) and 'mahjong_stage_session=;' in headers['set-cookie']
            assert headers['location'] == '/oauth2/signed-out'
            assert request(table_port, headers['location'])[0] == 200
            assert request(table_port, '/api/state')[0] == 302
            replay_status = request(table_port, '/api/state',
                                    headers={'Cookie': sessions[0]})[0]
            active_session = sign_in(login_code('friend-one'))
            assert request(table_port, '/api/state', headers={'Cookie': active_session})[0] == 200
            status, _, _ = request(identity_port, '/api/users/' + users[0][0], {
                'username': 'friend-one', 'firstName': '朋友', 'disabled': True,
            }, {'Cookie': admin}, method='PUT')
            assert status == 200, ('disable account', status)
            disabled_status = request(table_port, '/api/state',
                                      headers={'Cookie': active_session})[0]
            deadline = time.monotonic() + 3
            while disabled_status == 200 and time.monotonic() < deadline:
                time.sleep(.1)
                disabled_status = request(table_port, '/api/state',
                                          headers={'Cookie': active_session})[0]
            assert (replay_status, disabled_status) == (302, 302), (
                'logout replay / disabled account must be denied', replay_status, disabled_status)
            assert request(table_port, '/api/state', headers={'Cookie': sessions[1]})[0] == 200
            print('PASS: logout revokes copied cookies; disabled accounts lose access within 3s')

            # Cold backups are consistent only after all writers have stopped.
            sources = {}
            for service, target in (('identity', '/app/data'),
                                    ('web', '/var/lib/mahjong16')):
                mounts = json.loads(subprocess.check_output([
                    'docker', 'inspect', command('ps', '-q', service).strip(),
                    '--format', '{{json .Mounts}}'], encoding='utf-8'))
                sources[service] = next(m['Name'] for m in mounts if m['Destination'] == target)
            command('stop')
            backup = Path(directory) / 'backup'
            config.private_directory(backup)
            shutil.copytree(private, backup / 'config')

            def copy_volume(source: str, destination: str) -> None:
                result = subprocess.run([
                    'docker', 'run', '--rm', '--user', '0:0', '--network', 'none', '--read-only',
                    '--cap-drop', 'ALL', '--cap-add', 'CHOWN',
                    '--cap-add', 'DAC_OVERRIDE', '--cap-add', 'FOWNER',
                    '-v', source + ':/source:ro', '-v', destination + ':/destination',
                    os.environ['MAHJONG_IMAGE'], 'python', '-c',
                    'import pathlib,shutil,os,hashlib; '
                    's=pathlib.Path("/source"); d=pathlib.Path("/destination"); '
                    'shutil.copytree(s,d,dirs_exist_ok=True); '
                    'files=[p for p in s.rglob("*") if p.is_file()]; '
                    'assert all(hashlib.sha256(p.read_bytes()).digest() == '
                    'hashlib.sha256((d/p.relative_to(s)).read_bytes()).digest() for p in files); '
                    '[os.chown(p,10001,10001) for p in [d,*d.rglob("*")] '
                    'if __import__("sys").argv[1] == "restore"]',
                    'restore' if destination.startswith(project) else 'backup',
                ], timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                assert result.returncode == 0, result.stderr.decode()

            for service, volume in sources.items():
                path = backup / service
                config.private_directory(path)
                copy_volume(volume, str(path))
            restored = project + '-restore'
            compose = [*compose]
            compose[compose.index('-p') + 1] = restored
            projects.append(compose)
            env['MAHJONG_POCKET_CONFIG'] = str(backup / 'config')
            command('create', '--pull', 'never')
            for service, target in (('identity', '/app/data'),
                                    ('web', '/var/lib/mahjong16')):
                mounts = json.loads(subprocess.check_output([
                    'docker', 'inspect', command('ps', '-a', '-q', service).strip(),
                    '--format', '{{json .Mounts}}'], encoding='utf-8'))
                volume = next(m['Name'] for m in mounts if m['Destination'] == target)
                assert volume != sources[service]
                copy_volume(str(backup / service), volume)
            command('up', '-d', '--pull', 'never', '--wait')
            restored_identity_session = login_code('friend-two')
            status, _, payload = identity('/api/users/me', cookie=restored_identity_session)
            assert status == 200 and json.loads(payload)['id'] == users[1][0]
            restored_session = sign_in(restored_identity_session)
            status, _, _ = request(table_port, '/api/state', headers={'Cookie': restored_session})
            assert status == 200
            restored_web = command('ps', '-q', 'web').strip()
            result = json.loads(subprocess.check_output([
                'docker', 'exec', restored_web, 'python', '-c',
                'import sqlite3,json; '
                'c=sqlite3.connect("file:/var/lib/mahjong16/hands.sqlite3?mode=ro",uri=True); '
                'assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"; '
                'docs=[json.loads(r[0]) for r in c.execute('
                '"SELECT document FROM hands ORDER BY rowid")]; '
                'print(json.dumps({"players":[d["metadata"]["players"] for d in docs], '
                '"ids":[r[0] for r in c.execute("SELECT player_id FROM account_players")]})); '
                'c.close()',
            ], encoding='utf-8'))
            assert all(players in result['players'] for players in records)
            assert multiplayer[1]['player_id'] in result['ids']
            newest = result['players'][-1]
            assert newest[0]['player_id'] == multiplayer[1]['player_id']
            print('PASS: fresh volumes restore accounts, encrypted OIDC secrets, records and IDs')

            assert request(table_port, '/api/state',
                           headers={'Cookie': restored_session})[0] == 200
            command('stop', 'proxy')
            assert request(table_port, probe,
                           headers={'Cookie': restored_session})[0] in (502, 503)
            assert probe not in command('logs', '--no-color', 'web')
            print('PASS: verification-proxy outage fails closed even with an existing cookie')
            # A short lifetime exercises real expiry without waiting for the configured 12 hours.
            proxy_config = backup / 'config' / 'proxy.cfg'
            proxy_config.write_text(proxy_config.read_text(encoding='utf-8').replace(
                'cookie_expire = "12h"', 'cookie_expire = "5s"'), encoding='utf-8')
            command('up', '-d', '--no-deps', '--force-recreate', 'proxy')
            for _ in range(30):
                if request(table_port, '/')[0] == 302:
                    break
                time.sleep(1)
            else:
                raise AssertionError('Proxy did not recover after the expiry configuration')
            expiring_session = sign_in(restored_identity_session)
            assert request(table_port, '/api/state',
                           headers={'Cookie': expiring_session})[0] == 200
            time.sleep(6)
            assert request(table_port, '/api/state',
                           headers={'Cookie': expiring_session})[0] == 302
            print('PASS: an expired game cookie requires authentication again')
            live_session = sign_in(restored_identity_session)
            command('stop', 'identity')
            assert request(table_port, probe, headers={'Cookie': live_session})[0] in (502, 503)
            assert probe not in command('logs', '--no-color', 'web')
            command('up', '-d', '--wait', 'identity')
            live_session = sign_in(restored_identity_session)
            assert request(table_port, '/api/state', headers={'Cookie': live_session})[0] == 200
            command('stop', 'sessions')
            assert request(table_port, probe,
                           headers={'Cookie': live_session})[0] in (302, 500, 502, 503)
            assert probe not in command('logs', '--no-color', 'web')
            command('up', '-d', '--wait', 'sessions')
            assert request(table_port, '/api/state', headers={'Cookie': live_session})[0] == 302
            print('PASS: identity/Redis outages fail closed; lost sessions require login again')
            print('NOT CHECKED: native passkey enrollment, biometrics, iPhone or Windows')
        finally:
            # Only the two randomly named projects' disposable data is removed.
            for disposable in reversed(projects):
                subprocess.run([*disposable, 'down', '-v'], env=env, check=True, timeout=120,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


if __name__ == '__main__':
    main()
