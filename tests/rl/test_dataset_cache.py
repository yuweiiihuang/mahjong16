"""Tensor-cache parity, causal history, invalidation and atomic publication."""
import json
import random

import pytest

torch = pytest.importorskip('torch')

from domain.rules.ruleset import Ruleset
from rl.dataset import bc_batches, dataset_batches
from rl.encoding import encode
from rl.env import HandEpisode, training_spec
from rl.net import PolicyValueNet, load_checkpoint
from rl.train import bc_metrics, train_bc


@pytest.fixture
def data(tmp_path):
    spec = training_spec(Ruleset())
    obs = HandEpisode(2).current()
    obs['legal_actions'] = obs['legal_actions'][:3]
    forced = {**obs, 'drawn': 9, 'legal_actions': [{'type': 'PASS'}]}
    other = {**obs, 'player': (obs['player'] + 1) % 4}
    paths = {}
    for split, offset in [('train', 0), ('validation', 1_000_000_000)]:
        path = tmp_path / f'{split}.jsonl'
        header = {'dataset_version': 1, 'encoding_version': 1, 'spec': spec,
                  'split': split, 'start': 0, 'hands': 2}
        rows = []
        for seed in range(2):
            for seq, visible in enumerate([forced, other, obs, obs, forced, obs]):
                rows.append({'seed': seed + offset, 'seq': seq, 'observation': visible,
                             'label': 0, 'executed_action': visible['legal_actions'][-1]})
        path.write_text('\n'.join(json.dumps(r) for r in [header, *rows]) + '\n')
        paths[split] = path
    return paths, spec


def reference(path, spec, history, size=3):
    model = PolicyValueNet(1035, 82, hidden=16,
                           architecture='temporal' if history else 'mlp')
    result = []
    for rows in dataset_batches(path, spec, 'train', size=size, history=history):
        random.shuffle(rows)
        result.append((model.prepare([r['observation'] for r in rows]),
                       torch.tensor([r['label'] for r in rows]),
                       [(r['observation']['phase'],
                         r['observation']['legal_actions'][r['label']]['type']) for r in rows]))
    return result


@pytest.mark.parametrize('history', [False, True])
def test_cache_matches_original_packing_shuffle_and_rng(data, tmp_path, history, monkeypatch):
    paths, spec = data
    random.seed(17)
    expected = reference(paths['train'], spec, history)
    expected_rng = random.getstate()
    for cache in [None, tmp_path / 'cache', tmp_path / 'cache']:
        random.seed(17)
        actual = list(bc_batches(paths['train'], spec, 'train', size=3, history=history,
                                 shuffle=True, cache_dir=cache))
        assert random.getstate() == expected_rng
        assert [len(labels) for _, labels, _ in actual] == [3, 3, 2]
        for (inputs, labels, groups), (old_inputs, old_labels, old_groups) in zip(actual, expected):
            assert groups == old_groups
            assert torch.equal(labels, old_labels)
            for a, b in zip(inputs, old_inputs):
                torch.testing.assert_close(a, b, rtol=0, atol=0)
    # A warm read must not invoke JSONL validation/encoding again.
    import rl.dataset as module
    monkeypatch.setattr(module, 'dataset_batches', lambda *a, **k: pytest.fail('reparsed source'))
    assert len(list(bc_batches(paths['train'], spec, 'train', size=3, history=history,
                              cache_dir=tmp_path / 'cache'))) == 3


def test_cached_history_keeps_forced_and_executed_actions_and_resets_hands(data, tmp_path):
    paths, spec = data
    actual = list(bc_batches(paths['train'], spec, 'train', history=True,
                            cache_dir=tmp_path / 'cache'))[0]
    inputs, labels, _ = actual
    raw = [json.loads(line) for line in paths['train'].read_text().splitlines()[1:]]
    forced_state, forced_actions = encode(raw[0]['observation'])
    _, choice_actions = encode(raw[2]['observation'])
    assert inputs[-1].tolist() == [0, 1, 2, 3, 0, 1, 2, 3]
    assert labels.tolist() == [0] * 8
    torch.testing.assert_close(inputs[3][1, 0], torch.tensor(forced_state), rtol=0, atol=0)
    torch.testing.assert_close(inputs[4][1, 0], torch.tensor(forced_actions[0]), rtol=0, atol=0)
    torch.testing.assert_close(inputs[4][2, 1], torch.tensor(choice_actions[-1]), rtol=0, atol=0)


@pytest.mark.parametrize('architecture', ['mlp', 'transformer', 'hierarchical', 'temporal'])
def test_cached_bc_preserves_weights_adam_rng_and_validation(data, tmp_path, architecture):
    paths, spec = data
    torch.set_num_threads(1)
    checkpoints = []
    for name, cache in [('raw', None), ('cached', tmp_path / 'cache')]:
        checkpoint = tmp_path / f'{name}.pt'
        train_bc(paths['train'], paths['validation'], checkpoint, epochs=3, seed=29,
                 architecture=architecture, cache_dir=cache)
        checkpoints.append(torch.load(checkpoint, weights_only=True))
    a, b = checkpoints
    assert a['progress']['history'] == b['progress']['history']
    assert a['progress']['choices_seen'] == b['progress']['choices_seen'] == 24
    assert a['python_rng'] == b['python_rng']
    assert torch.equal(a['torch_rng'], b['torch_rng'])
    assert all(torch.equal(t, b['model'][key]) for key, t in a['model'].items())
    for key, state in a['optimizer']['state'].items():
        assert all(torch.equal(t, b['optimizer']['state'][key][field])
                   for field, t in state.items())
    model, _ = load_checkpoint(tmp_path / 'raw.pt', spec)
    assert bc_metrics(model, paths['validation'], spec, 'validation') == bc_metrics(
        model, paths['validation'], spec, 'validation', cache_dir=tmp_path / 'cache')


def test_source_changes_invalidate_cache_and_reject_bad_history(data, tmp_path):
    paths, spec = data
    cache = tmp_path / 'cache'
    args = (paths['train'], spec, 'train')
    list(bc_batches(*args, history=True, cache_dir=cache))
    records = [json.loads(line) for line in paths['train'].read_text().splitlines()]
    records[3]['label'] = 1
    paths['train'].write_text('\n'.join(json.dumps(r) for r in records) + '\n')
    changed = list(bc_batches(*args, history=True, cache_dir=cache))
    assert changed[0][1][1] == 1
    assert len(list(cache.glob('*/manifest.json'))) == 2
    records[3]['seq'] = 99
    paths['train'].write_text('\n'.join(json.dumps(r) for r in records) + '\n')
    with pytest.raises(ValueError, match='consecutive'):
        list(bc_batches(*args, history=True, cache_dir=cache))
    assert len(list(cache.glob('*/manifest.json'))) == 2
    assert not list(cache.glob('.building-*'))


@pytest.mark.parametrize('damage', ['modified', 'missing', 'extra', 'contract'])
def test_damaged_cache_is_rejected(data, tmp_path, damage):
    paths, spec = data
    cache = tmp_path / 'cache'
    args = (paths['train'], spec, 'train')
    list(bc_batches(*args, cache_dir=cache))
    folder = next(cache.iterdir())
    part = next(folder.glob('*.pt'))
    if damage == 'modified':
        with part.open('ab') as handle:
            handle.write(b'corrupt')
    elif damage == 'missing':
        part.unlink()
    elif damage == 'extra':
        (folder / 'unexpected.pt').write_bytes(part.read_bytes())
    else:
        manifest = json.loads((folder / 'manifest.json').read_text())
        manifest['contract']['split'] = 'test'
        (folder / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='cache'):
        list(bc_batches(*args, cache_dir=cache))


def test_directory_cache_checks_split_overlap_and_independent_shard_batches(data, tmp_path):
    paths, spec = data
    folder = tmp_path / 'shards'
    folder.mkdir()
    original = paths['train'].read_text()
    (folder / 'train-a.jsonl').write_text(original)
    cache = tmp_path / 'cache'
    assert len(list(bc_batches(folder, spec, 'train', size=3, cache_dir=cache))) == 3
    with pytest.raises(ValueError, match='split'):
        list(bc_batches(paths['train'], spec, 'validation', cache_dir=cache))
    with pytest.raises(ValueError, match='split'):
        list(bc_batches(paths['train'], {**spec, 'view_version': 999}, 'train', cache_dir=cache))
    (folder / 'train-b.jsonl').write_text(original)
    with pytest.raises(ValueError, match='overlapping'):
        list(bc_batches(folder, spec, 'train', cache_dir=cache))


def test_failed_build_publishes_no_partial_cache(data, tmp_path, monkeypatch):
    paths, spec = data
    import rl.dataset as module
    original = module.batch
    calls = 0

    def interrupted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise InterruptedError('simulated build failure')
        return original(*args, **kwargs)

    monkeypatch.setattr(module, 'batch', interrupted)
    cache = tmp_path / 'cache'
    with pytest.raises(InterruptedError):
        list(bc_batches(paths['train'], spec, 'train', size=3, cache_dir=cache))
    assert not list(cache.iterdir())
    monkeypatch.setattr(module, 'batch', original)
    assert len(list(bc_batches(paths['train'], spec, 'train', size=3, cache_dir=cache))) == 3
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in cache.glob('*/*'))
