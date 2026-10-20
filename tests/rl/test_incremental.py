"""Contracts for continued BC, learner-labelled histories and privileged isolation."""
from copy import deepcopy
import json
import random

import pytest

torch = pytest.importorskip('torch')

from bots.greedy import GreedyBotStrategy
from domain.rules.ruleset import Ruleset
from rl.asymmetric import IndependentCritic, opponent_hands, train_privileged_ppo
from rl.dagger import collect_dagger
from rl.encoding import encode
from rl.env import HandEpisode, LearnerEpisode, training_spec
from rl.finetune import continue_bc
from rl.history import DecisionHistory
from rl.net import PolicyValueNet, load_checkpoint, save_checkpoint
from rl.selfplay import generate
from rl.train import dataset_batches


@pytest.fixture
def bc(tmp_path):
    torch.set_num_threads(1)
    torch.manual_seed(7)
    random.seed(7)
    state, actions = encode(HandEpisode(0).current())
    model = PolicyValueNet(len(state), len(actions[0]), hidden=16, architecture='temporal')
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    path = tmp_path / 'bc.pt'
    save_checkpoint(path, model, training_spec(Ruleset()), stage='bc', optimizer=optimizer,
                    progress={})
    return path


def test_dagger_labels_and_history_follow_different_actions(bc, tmp_path):
    path = tmp_path / 'train.jsonl'
    counts = collect_dagger(bc, path, start=20_000_000, hands=1)
    raw = [json.loads(line) for line in path.read_text().splitlines()[1:]]
    assert len(raw) == counts['decisions'] and counts['disagreements'] > 0
    model, _ = load_checkpoint(bc, training_spec(Ruleset()))
    teacher = GreedyBotStrategy()
    episode = LearnerEpisode(20_000_000, 0)
    memory = DecisionHistory()
    choice_histories = []
    for row in raw:
        obs = episode.current()
        assert obs == row['observation']
        assert obs['legal_actions'][row['label']] == teacher.choose(obs)
        assert row['executed_action'] == model.choose(memory.observe(obs))
        if len(obs['legal_actions']) > 1:
            choice_histories.append(deepcopy(memory.observe(obs)['decision_history']))
        memory.append(obs, row['executed_action'])
        episode.step(row['executed_action'])
    assert episode.current() is None
    rows = [row for group in dataset_batches(path, training_spec(Ruleset()), 'train',
                                             history=True) for row in group]
    assert [row['observation']['decision_history'] for row in rows] == choice_histories
    raw[0]['executed_action'] = {'type': 'INVALID'}
    lines = path.read_text().splitlines()
    lines[1] = json.dumps(raw[0])
    path.write_text('\n'.join(lines) + '\n')
    with pytest.raises(ValueError, match='executed action'):
        list(dataset_batches(path, training_spec(Ruleset()), 'train', history=True))


def test_directory_shards_reject_overlap_and_keep_history_local(tmp_path):
    generate(tmp_path / 'train-a.jsonl', 1, split='train', start=0)
    generate(tmp_path / 'train-b.jsonl', 1, split='train', start=1)
    spec = training_spec(Ruleset())
    rows = [r for g in dataset_batches(tmp_path, spec, 'train', history=True) for r in g]
    assert {r['seed'] for r in rows} == {0, 1}
    (tmp_path / 'train-copy.jsonl').write_bytes((tmp_path / 'train-a.jsonl').read_bytes())
    with pytest.raises(ValueError, match='overlapping'):
        list(dataset_batches(tmp_path, spec, 'train', history=True))


@pytest.mark.parametrize('cached', [False, True])
def test_bc_complete_epoch_resume_restores_adam_and_rng(bc, tmp_path, monkeypatch, cached):
    import rl.finetune as module
    generate(tmp_path / 'train.jsonl', 1, split='train')
    generate(tmp_path / 'validation.jsonl', 1, split='validation')
    args = (bc, tmp_path / 'train.jsonl', tmp_path / 'validation.jsonl')
    cache = tmp_path / 'tensor-cache' if cached else None
    continue_bc(*args, tmp_path / 'full', epochs=2, patience=3, cache_dir=cache)
    original = module.save_checkpoint

    def stop_after_epoch(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path.name == 'epoch-001.pt':
            raise InterruptedError('simulated interruption')

    monkeypatch.setattr(module, 'save_checkpoint', stop_after_epoch)
    with pytest.raises(InterruptedError):
        continue_bc(*args, tmp_path / 'resumed', epochs=2, patience=3, cache_dir=cache)
    monkeypatch.setattr(module, 'save_checkpoint', original)
    continue_bc(*args, tmp_path / 'resumed', epochs=2, patience=3)
    a = torch.load(tmp_path / 'full/epoch-002.pt', weights_only=True)
    b = torch.load(tmp_path / 'resumed/epoch-002.pt', weights_only=True)
    assert all(torch.equal(v, b['model'][k]) for k, v in a['model'].items())
    assert torch.equal(a['torch_rng'], b['torch_rng'])
    assert a['python_rng'] == b['python_rng']
    for key, state in a['optimizer']['state'].items():
        assert all(torch.equal(v, b['optimizer']['state'][key][k]) for k, v in state.items())
    with pytest.raises(ValueError, match='settings changed'):
        continue_bc(*args, tmp_path / 'resumed', epochs=3)


def test_privileged_actor_and_history_are_isolated(bc):
    spec = training_spec(Ruleset())
    actor, _ = load_checkpoint(bc, spec)
    critic, _ = load_checkpoint(bc, spec)
    model = IndependentCritic(actor, critic)
    obs = DecisionHistory().observe(HandEpisode(0).current())
    obs['critic_hand_counts'] = [0.] * 102
    changed = deepcopy(obs)
    changed['critic_hand_counts'] = [1.] * 102
    # Make the critic sensitive to hidden counts; logits must still be identical.
    with torch.no_grad():
        model.value_head[0].weight[:, 16:].fill_(.01)
        model.value_head[2].weight.fill_(.1)
    logits, values = model(*model.prepare([obs, changed]))
    torch.testing.assert_close(logits[0], logits[1], rtol=0, atol=0)
    assert values[0] != values[1]
    logits[0].logsumexp(-1).backward()
    assert all(p.grad is None for p in model.critic.parameters())
    assert all(p.grad is None for p in model.value_head.parameters())
    del changed['critic_hand_counts']
    with pytest.raises(ValueError, match='Missing'):
        model.prepare([changed])


def test_opponent_snapshot_is_relative_and_copied():
    env = HandEpisode(0).env
    for i, player in enumerate(env.players):
        player.hand, player.drawn = [i] * (i + 1), None
    counts = opponent_hands(env, 2)
    assert counts[3] == 1. and counts[34] == .25 and counts[68 + 1] == .5
    assert sum(counts) == 1.75
    env.players[3].hand.clear()
    assert counts[3] == 1.


def test_privileged_joint_resume_and_actor_export(bc, tmp_path, monkeypatch):
    import rl.asymmetric as module
    original = module.collect_privileged

    def stop_second(model, *, seed, start, hands):
        if start:
            raise InterruptedError('simulated interruption')
        return original(model, seed=seed, start=start, hands=hands)

    train_privileged_ppo(bc, tmp_path / 'full', updates=2, hands=1, device='cpu')
    monkeypatch.setattr(module, 'collect_privileged', stop_second)
    with pytest.raises(InterruptedError):
        train_privileged_ppo(bc, tmp_path / 'resume', updates=2, hands=1, device='cpu')
    monkeypatch.setattr(module, 'collect_privileged', original)
    path = train_privileged_ppo(bc, tmp_path / 'resume', updates=2, hands=1, device='cpu')
    a = torch.load(tmp_path / 'full/joint-002.pt', weights_only=True)
    b = torch.load(tmp_path / 'resume/joint-002.pt', weights_only=True)
    assert all(torch.equal(v, b['model'][k]) for k, v in a['model'].items())
    assert torch.equal(a['torch_rng'], b['torch_rng'])
    assert a['python_rng'] == b['python_rng']
    for key, state in a['optimizer']['state'].items():
        assert all(torch.equal(v, b['optimizer']['state'][key][k]) for k, v in state.items())
    actor, saved = load_checkpoint(path, training_spec(Ruleset()))
    assert saved['stage'] == 'ppo-actor' and saved['progress']['hands'] == 2
    assert all(torch.equal(v, b['model']['actor.' + k]) for k, v in actor.state_dict().items())


@pytest.mark.parametrize('losses, selected', [([1., .9998, .9997], 2), ([1., 1.1, 1.2], 0)])
def test_bc_stopping_is_separate_from_actual_lowest_ce(bc, tmp_path, monkeypatch,
                                                     losses, selected):
    import rl.finetune as module
    generate(tmp_path / 'train.jsonl', 1, split='train')
    generate(tmp_path / 'validation.jsonl', 1, split='validation')
    measurements = iter(losses)

    def metrics(*args, **kwargs):
        return {'all': {'count': 1, 'accuracy': .5, 'loss': next(measurements)}}

    monkeypatch.setattr(module, 'bc_metrics', metrics)
    output = tmp_path / 'continued'
    path = continue_bc(bc, tmp_path / 'train.jsonl', tmp_path / 'validation.jsonl',
                       output, epochs=10, patience=2, min_delta=.001)
    assert path.name == f'epoch-{selected:03}.pt'
    assert [p.name for p in sorted(output.glob('epoch-*.pt'))] == [
        'epoch-000.pt', 'epoch-001.pt', 'epoch-002.pt']


def test_fresh_bc_initialization_and_complete_epoch_resume(tmp_path, monkeypatch):
    import rl.finetune as module
    generate(tmp_path / 'train.jsonl', 1, split='train')
    generate(tmp_path / 'validation.jsonl', 1, split='validation')
    args = (tmp_path / 'train.jsonl', tmp_path / 'validation.jsonl')
    module.fresh_bc(*args, tmp_path / 'fresh', epochs=2, hidden=16)
    original = module.save_checkpoint

    def interrupt(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path.name == 'epoch-001.pt':
            raise InterruptedError('after complete epoch')

    monkeypatch.setattr(module, 'save_checkpoint', interrupt)
    with pytest.raises(InterruptedError):
        module.fresh_bc(*args, tmp_path / 'resume-fresh', epochs=2, hidden=16)
    monkeypatch.setattr(module, 'save_checkpoint', original)
    module.fresh_bc(*args, tmp_path / 'resume-fresh', epochs=2, hidden=16)
    a = torch.load(tmp_path / 'fresh/epoch-002.pt', weights_only=True)
    b = torch.load(tmp_path / 'resume-fresh/epoch-002.pt', weights_only=True)
    assert all(torch.equal(t, b['model'][k]) for k, t in a['model'].items())
    assert torch.equal(a['torch_rng'], b['torch_rng']) and a['python_rng'] == b['python_rng']
    for key, state in a['optimizer']['state'].items():
        assert all(torch.equal(t, b['optimizer']['state'][key][k]) for k, t in state.items())
    initial = torch.load(tmp_path / 'fresh/initial.pt', weights_only=True)
    assert initial['optimizer']['state'] == {}
    assert initial['progress']['fresh_contract']['seed'] == 29
    with pytest.raises(ValueError, match='initialization contract'):
        module.fresh_bc(*args, tmp_path / 'fresh', seed=30, epochs=2, hidden=16)


def test_actor_kl_stop_does_not_truncate_or_update_critic_actor(bc, monkeypatch):
    import rl.ppo_stopped as module
    from rl.asymmetric import VisibleReference, collect_privileged
    spec = training_spec(Ruleset())
    actor, _ = load_checkpoint(bc, spec)
    critic, _ = load_checkpoint(bc, spec)
    reference, _ = load_checkpoint(bc, spec)
    reference.requires_grad_(False)
    model = IndependentCritic(actor, critic)
    model.eval()
    rows, _ = collect_privileged(model, seed=29, start=0, hands=1)
    before = {k: t.clone() for k, t in model.value_head.state_dict().items()}
    ao = torch.optim.Adam([p for p in actor.parameters() if p.requires_grad], lr=3e-4)
    co = torch.optim.Adam([p for m in [model.critic, model.value_head]
                          for p in m.parameters() if p.requires_grad], lr=3e-4)
    original = module._optimize
    stopped_actor = {}

    def step(loss, owner, optimizer):
        original(loss, owner, optimizer)
        if owner is actor:
            stopped_actor.update({k: t.clone() for k, t in actor.state_dict().items()})
        else:
            assert all(torch.equal(t, stopped_actor[k]) for k, t in actor.state_dict().items())

    monkeypatch.setattr(module, '_optimize', step)
    metrics = module.update_independent(model, ao, co, rows,
        reference=VisibleReference(reference), target_kl=0., actor_epochs=4, critic_epochs=3)
    assert metrics['actor_early_stopped'] and metrics['actor_optimizer_steps'] == 1
    assert metrics['critic_optimizer_steps'] == 3 * ((len(rows) + 255) // 256)
    assert any(not torch.equal(t, before[k]) for k, t in model.value_head.state_dict().items())
    assert all(p.grad is None for p in actor.parameters())
    assert metrics['rollout_exact_old_kl'] > 0


def test_stopped_ppo_resume_pending_evaluation_and_two_optimizers(bc, tmp_path, monkeypatch):
    import rl.ppo_stopped as module
    args = {'updates': 3, 'hands': 1, 'device': 'cpu', 'eval_every': 1,
            'min_updates': 0, 'patience': 2, 'min_delta': 20.,
            'actor_epochs': 1, 'critic_epochs': 1, 'target_kl': 0.}
    score = lambda path, index: -float(index)
    module.train_stopped_ppo(bc, tmp_path / 'stop-full', evaluate=score, **args)
    original = module.collect_privileged
    collected = []

    def collect(model, *, seed, start, hands):
        collected.append(start)
        return original(model, seed=seed, start=start, hands=hands)

    def interrupt(path, index):
        if index == 1:
            raise InterruptedError('joint persisted, development evaluation pending')
        return score(path, index)

    monkeypatch.setattr(module, 'collect_privileged', collect)
    with pytest.raises(InterruptedError):
        module.train_stopped_ppo(bc, tmp_path / 'stop-resume', evaluate=interrupt, **args)
    export = module.train_stopped_ppo(bc, tmp_path / 'stop-resume', evaluate=score, **args)
    assert collected == [0, 1]
    a = torch.load(tmp_path / 'stop-full/joint-002.pt', weights_only=True)
    b = torch.load(tmp_path / 'stop-resume/joint-002.pt', weights_only=True)
    assert all(torch.equal(t, b['model'][k]) for k, t in a['model'].items())
    assert torch.equal(a['torch_rng'], b['torch_rng']) and a['python_rng'] == b['python_rng']
    for opt in ['actor_optimizer', 'critic_optimizer']:
        for key, state in a[opt]['state'].items():
            assert all(torch.equal(t, b[opt]['state'][key][k]) for k, t in state.items())
    model, metadata = load_checkpoint(export, training_spec(Ruleset()))
    initial, _ = load_checkpoint(bc, training_spec(Ruleset()))
    assert metadata['progress']['selected_update'] == 0
    assert metadata['progress']['stop_reason'] == 'patience'
    assert metadata['progress']['hands'] == 2
    assert all(torch.equal(t, initial.state_dict()[k]) for k, t in model.state_dict().items())
    # Completion is idempotent and never collects a new rollout.
    module.train_stopped_ppo(bc, tmp_path / 'stop-resume', evaluate=score, **args)
    assert collected == [0, 1]


def test_bc_resource_guard_stops_after_recoverable_epoch(bc, tmp_path):
    generate(tmp_path / 'train.jsonl', 1, split='train')
    generate(tmp_path / 'validation.jsonl', 1, split='validation')
    args = (bc, tmp_path / 'train.jsonl', tmp_path / 'validation.jsonl')
    output = tmp_path / 'guarded'

    def guard():
        if (output / 'epoch-001.pt').exists():
            raise MemoryError('simulated reserve exhaustion')

    with pytest.raises(MemoryError):
        continue_bc(*args, output, epochs=2, resource_check=guard)
    assert (output / 'epoch-001.pt').exists()
    continue_bc(*args, output, epochs=2, resource_check=lambda: None)
    summary = json.loads((output / 'training-summary.json').read_text())
    assert summary['completed_epochs'] == 2 and summary['stop_reason'] == 'budget'
    assert summary['contract']['resource_checks']
