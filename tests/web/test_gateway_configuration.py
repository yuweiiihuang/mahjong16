"""Private credentials and the public authentication origin are deployment boundaries."""

import importlib.util
import json
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gateway_config', ROOT / 'deploy/gateway/configure.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


@pytest.mark.parametrize('url', [
    'http://table.example', 'https://user:secret@table.example',
    'https://table.example/auth', 'https://table.example?bypass=1',
    'https://table.example/#fragment', 'https://',
    'https://table.example:not-a-port', 'https://table.example:65536',
    'https://table.example:0',
])
def test_rejects_invalid_public_origins(url):
    with pytest.raises(ValueError):
        gateway.auth_configuration(url)


def test_configuration_has_one_https_origin_and_denies_other_users():
    config = gateway.auth_configuration('https://table.example/')
    assert config['access_control']['default_policy'] == 'deny'
    assert config['access_control']['rules'] == [
        {'domain': 'table.example', 'policy': 'one_factor', 'subject': ['group:players']}]
    cookie = config['session']['cookies'][0]
    assert cookie['authelia_url'] == 'https://table.example/auth/'
    assert cookie['default_redirection_url'] == 'https://table.example/'


def test_initialization_is_private_and_never_overwrites(tmp_path, monkeypatch, capsys):
    password = 'X' * 32
    monkeypatch.setattr(gateway.subprocess, 'check_output', lambda *a, **kw:
                        f'Random Password: {password}\nDigest: $argon2id$test-only\n')
    directory = tmp_path / 'private'
    gateway.initialize(directory, 'https://table.example', 'friend')
    original = (directory / 'users.yml').read_bytes()
    assert json.loads(original)['users']['friend']['groups'] == ['players']
    assert password in (directory / 'login.txt').read_text()
    assert password not in capsys.readouterr().out
    if os.name != 'nt':
        assert directory.stat().st_mode & 0o777 == 0o700
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir())
    with pytest.raises(FileExistsError):
        gateway.initialize(directory, 'https://table.example', 'friend')
    assert (directory / 'users.yml').read_bytes() == original


def test_refuses_credentials_inside_repository():
    with pytest.raises(ValueError, match='outside'):
        gateway.initialize(ROOT / 'private-gateway-credentials', 'https://table.example', 'friend')
