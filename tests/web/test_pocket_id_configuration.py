"""The passwordless experiment must not reuse production secrets or expose an HTTP login."""

import importlib.util
import json
import os
from pathlib import Path
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'pocket_config', ROOT / 'deploy/pocket-id/configure.py')
pocket = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pocket)


@pytest.mark.skipif(os.name == 'nt', reason='Local proof of concept supports macOS/Linux only')
def test_local_configuration_is_private_and_never_overwrites(tmp_path, capsys):
    directory = tmp_path / 'private'
    pocket.initialize(directory, 18080, 18081)
    proxy = tomllib.loads((directory / 'proxy.cfg').read_text(encoding='utf-8'))
    client = json.loads((directory / 'client.json').read_text(encoding='utf-8'))
    assert proxy['oidc_issuer_url'] == 'http://localhost:18081'
    assert proxy['redirect_url'] == 'http://localhost:18080/oauth2/callback'
    assert client['callbackURLs'] == [proxy['redirect_url']]
    assert client['pkceEnabled'] and proxy['code_challenge_method'] == 'S256'
    assert proxy['session_store_type'] == 'redis'
    assert proxy['redis_connection_url'] == 'redis://sessions:6379/0'
    assert 'offline_access' in proxy['scope'].split()
    assert proxy['cookie_refresh'] == '1s'
    assert proxy['client_secret'] == (directory / 'client-secret.txt').read_text(encoding='utf-8')
    assert proxy['client_secret'] not in capsys.readouterr().out
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in directory.iterdir())
    original = (directory / 'encryption-key.txt').read_bytes()
    with pytest.raises(FileExistsError):
        pocket.initialize(directory)
    assert (directory / 'encryption-key.txt').read_bytes() == original


@pytest.mark.parametrize(('table', 'identity'), [
    (0, 18081), (18080, 65536), (80, 18081), (18080, 18080),
])
def test_invalid_ports_do_not_create_secrets(tmp_path, table, identity):
    directory = tmp_path / 'private'
    with pytest.raises(ValueError):
        pocket.initialize(directory, table, identity)
    assert not directory.exists()


def test_refuses_credentials_inside_repository():
    with pytest.raises(ValueError, match='outside'):
        pocket.initialize(ROOT / 'private-pocket-config')


def test_funnel_configuration_uses_secure_separate_origins(tmp_path):
    directory = tmp_path / 'private'
    pocket.initialize(directory, 18084, 18085, 'https://example.tail123.ts.net')
    proxy = tomllib.loads((directory / 'proxy.cfg').read_text(encoding='utf-8'))
    assert proxy['oidc_issuer_url'] == 'https://example.tail123.ts.net:8443'
    assert proxy['redirect_url'] == 'https://example.tail123.ts.net/oauth2/callback'
    assert proxy['cookie_secure'] and proxy['cookie_name'].startswith('__Host-')
    assert 'http://localhost' not in (directory / 'pocket.env').read_text(encoding='utf-8')


@pytest.mark.parametrize('url', [
    'http://example.ts.net', 'https://example.ts.net/path', 'https://example.ts.net:443',
    'https://user@example.ts.net', 'https://example.ts.net?query=1',
    'https://example.ts.net#fragment', 'https://example.com',
])
def test_invalid_public_origin_creates_no_credentials(tmp_path, url):
    directory = tmp_path / 'private'
    with pytest.raises(ValueError):
        pocket.initialize(directory, public_url=url)
    assert not directory.exists()


def test_public_bootstrap_requires_matching_origin_and_loopback_port(tmp_path):
    pocket.initialize(tmp_path / 'private', public_url='https://example.ts.net')
    with pytest.raises(ValueError, match='port'):
        pocket.bootstrap(tmp_path / 'private', 'https://example.ts.net')
    with pytest.raises(ValueError, match='match'):
        pocket.bootstrap(tmp_path / 'private', 'https://other.ts.net', 18085)


def test_invalid_local_client_is_rejected_before_creating_an_administrator(tmp_path, monkeypatch):
    private = tmp_path / 'private'
    pocket.initialize(private)
    (private / 'client.json').write_text('invalid JSON', encoding='utf-8')

    def unexpected_request(*args, **kwargs):
        raise AssertionError('Local input errors must not leave an incomplete administrator')

    monkeypatch.setattr(pocket.urllib.request, 'urlopen', unexpected_request)
    with pytest.raises(json.JSONDecodeError):
        pocket.bootstrap(private)


@pytest.mark.parametrize('origin', [
    'http://attacker.example', 'http://localhost@attacker.example',
    'http://localhost:18081/api', 'http://localhost:18081?redirect=evil',
])
def test_bootstrap_never_sends_secrets_to_other_origins(tmp_path, origin):
    (tmp_path / 'pocket.env').write_text('APP_URL=' + origin)
    with pytest.raises(ValueError, match='localhost'):
        pocket.bootstrap(tmp_path)
