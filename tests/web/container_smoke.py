"""Exercise a disposable Docker table over HTTP; creates and leaves a test room."""
import argparse
import json
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8002')
    parser.add_argument('--password-file', type=Path, required=True)
    args = parser.parse_args()
    password = args.password_file.read_text(encoding='utf-8').strip()
    url = args.url.rstrip('/')

    def request(client, path, data=None, form=False):
        body = None if data is None else (
            urlencode(data).encode() if form else json.dumps(data).encode())
        headers = {'Content-Type': 'application/x-www-form-urlencoded' if form
                   else 'application/json'}
        try:
            response = client.open(Request(url + path, body, headers), timeout=25)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    host, guest = [build_opener(HTTPCookieProcessor(CookieJar())) for _ in range(2)]
    status, page = request(host, '/')
    assert status == 200 and b'/access/login' in page
    assert request(host, '/api/state')[0] == 401
    assert request(host, '/access/login', {'password': 'incorrect'}, form=True)[0] == 401
    for client in (host, guest):
        status, page = request(client, '/access/login', {'password': password}, form=True)
        assert status == 200 and b'id="hand"' in page
        for path in ('/app.js', '/style.css', '/table3d.js', '/assets/tiles/32.svg'):
            assert request(client, path)[0] == 200
        assert request(client, '/.env')[0] == 404
        assert request(client, '/assets/')[0] == 404
    status, body = request(host, '/api/rooms', {'name': '容器測試'})
    state = json.loads(body)
    assert status == 200 and state['room']['host']
    try:
        status, body = request(guest, '/api/room/join',
                               {'code': state['room']['code'], 'name': '測試朋友'})
        assert status == 200 and not json.loads(body)['room']['host']
        status, body = request(host, '/api/room/start', {})
        assert status == 200 and json.loads(body)['room']['started']
        status, body = request(host, '/api/room/state')
        state = json.loads(body)
        if not state['legal_actions']:
            status, body = request(host, f"/api/room/state?after={state['version']}")
            state = json.loads(body)
        assert status == 200 and state['legal_actions']
        action = {'version': state['version'], 'request_id': 'container-smoke',
                  'action': state['legal_actions'][0]}
        assert request(host, '/api/room/action', action)[0] == 200
        assert request(guest, '/api/state')[0] == 200
    finally:
        request(guest, '/api/room/leave', {})
        request(host, '/api/room/leave', {})
    print('Container login, assets, multiplayer and action checks passed.')


if __name__ == '__main__':
    main()
