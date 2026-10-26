"""Build output must never change or recursively copy the upstream checkout."""
from pathlib import Path

import pytest

from scripts.build_meowcats import build


@pytest.mark.parametrize('target', ['.', 'native', 'native/../nested'])
def test_output_inside_upstream_is_rejected_before_any_work(tmp_path, monkeypatch, target):
    upstream = tmp_path / 'upstream'
    upstream.mkdir()

    def unexpected(*args, **kwargs):
        pytest.fail('Unsafe output must be rejected before querying Git or writing files')

    monkeypatch.setattr('scripts.build_meowcats.subprocess.check_output', unexpected)
    with pytest.raises(ValueError, match='outside the upstream'):
        build(upstream, upstream / Path(target))
    assert list(upstream.iterdir()) == []
