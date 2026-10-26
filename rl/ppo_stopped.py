"""Exact rollout-KL actor stopping with an independently bounded privileged critic."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Callable

import torch
from torch import nn
from torch.distributions import Categorical
from torch.nn import functional as F

from app.hand_store import open_private_record, write_private_record
from domain.rules.ruleset import Ruleset
from rl.asymmetric import IndependentCritic, VisibleReference, collect_privileged
from rl.env import training_spec
from rl.finetune import fingerprint
from rl.net import (configure_determinism, get_device_rng_state, load_checkpoint,
                    save_checkpoint, set_device_rng_state)
from rl.stopping import Patience
from rl.train import _optimize, _policy_kl, ppo_diagnostics


def old_distribution(rows: list[dict], logits: torch.Tensor) -> torch.Tensor:
    """Pack frozen legal-action log probabilities, excluding padded candidates."""
    old = torch.full_like(logits, -torch.inf)
    for i, row in enumerate(rows):
        size = len(row['observation']['legal_actions'])
        values = torch.tensor(row['old_log_probs'], device=logits.device)
        if (len(values) != size or not torch.isfinite(values).all()
                or not torch.isclose(values.logsumexp(0), values.new_tensor(0.), atol=1e-5)):
            raise ValueError('Invalid frozen rollout action distribution')
        if not torch.isfinite(logits[i, :size]).all() or torch.isfinite(logits[i, size:]).any():
            raise ValueError('Current legal candidates differ from frozen rollout')
        old[i, :size] = values
    return old


@torch.no_grad()
def rollout_exact_kl(model: IndependentCritic, rows: list[dict]) -> float:
    """Mean KL(old || current) on observed choice states, exact over legal actions."""
    total, count = 0., 0
    for offset in range(0, len(rows), 256):
        group = [r for r in rows[offset:offset + 256]
                 if len(r['observation']['legal_actions']) > 1]
        if not group:
            continue
        inputs = model.prepare([r['observation'] for r in group])
        logits, _ = model(*inputs)
        divergence = _policy_kl(old_distribution(group, logits), logits)
        if not torch.isfinite(divergence).all():
            raise RuntimeError('Nonfinite rollout KL')
        total += float(divergence.sum())
        count += len(group)
    return max(0., total / count) if count else 0.


def update_independent(model: IndependentCritic, actor_optimizer: torch.optim.Optimizer,
                       critic_optimizer: torch.optim.Optimizer, rows: list[dict], *,
                       reference: VisibleReference, actor_epochs: int = 4,
                       critic_epochs: int = 4, target_kl: float = .03,
                       bc_kl_coef: float = .2, schedule_seed: int = 0,
                       schedule_update: int = 0) -> dict:
    """Stop actor after KL excess; always finish the independent critic epoch cap."""
    if (not rows or actor_epochs <= 0 or critic_epochs <= 0 or target_kl < 0
            or not math.isfinite(target_kl) or not math.isfinite(bc_kl_coef)
            or bc_kl_coef < 0):
        raise ValueError('Invalid independent PPO update budget')
    actor_ids = {id(p) for g in actor_optimizer.param_groups for p in g['params']}
    critic_ids = {id(p) for g in critic_optimizer.param_groups for p in g['params']}
    expected_actor = {id(p) for p in model.actor.parameters() if p.requires_grad}
    value_module = nn.ModuleList([model.critic, model.value_head])
    expected_critic = {id(p) for p in value_module.parameters() if p.requires_grad}
    if actor_ids != expected_actor or critic_ids != expected_critic or actor_ids & critic_ids:
        raise ValueError('Actor and critic optimizers must own disjoint complete parameters')
    device = next(model.parameters()).device
    advantages = torch.tensor([r['return'] - r['old_value'] for r in rows], device=device)
    choices = torch.tensor([len(r['observation']['legal_actions']) > 1 for r in rows],
                           device=device)
    if choices.sum() > 1:
        selected = advantages[choices]
        advantages = (advantages - selected.mean()) / selected.std(unbiased=False).clamp_min(1e-8)
    # Precompute both schedules: actor stopping must not alter critic minibatches.
    schedules = {}
    for name, epochs in [('actor', actor_epochs), ('critic', critic_epochs)]:
        generator = random.Random(f'{schedule_seed}:{schedule_update}:{name}:v1')
        schedules[name] = []
        for _ in range(epochs):
            order = list(range(len(rows)))
            generator.shuffle(order)
            schedules[name].append(order)
    schedule = {'version': 1, 'seed': schedule_seed, 'update': schedule_update,
                'rows_sha256': hashlib.sha256(json.dumps(
                    rows, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                'order_sha256': {name: hashlib.sha256(json.dumps(orders).encode()).hexdigest()
                                 for name, orders in schedules.items()}}
    actor_steps, critic_steps, stopped = 0, 0, False
    exact_kl = rollout_exact_kl(model, rows)
    if exact_kl > 1e-5:
        raise ValueError('Rollout old distribution does not match initial actor')
    kl_trace = []
    for order in schedules['actor']:
        for offset in range(0, len(order), 256):
            indices = order[offset:offset + 256]
            active = choices[indices]
            if not active.any():
                continue
            group = [rows[i] for i in indices]
            inputs = model.prepare([r['observation'] for r in group])
            logits, _ = model(*inputs)
            dist = Categorical(logits=logits)
            labels = torch.tensor([r['label'] for r in group], device=device)
            log_ratio = dist.log_prob(labels) - torch.tensor(
                [r['old_log_prob'] for r in group], device=device)
            ratio = log_ratio.exp()
            surrogate = torch.minimum(ratio * advantages[indices],
                                      ratio.clamp(.8, 1.2) * advantages[indices])
            with torch.no_grad():
                reference_logits, _ = reference(*inputs)
            bc_kl = _policy_kl(logits, reference_logits)[active].mean()
            entropy = dist.entropy()[active].mean()
            actor_loss = -surrogate[active].mean() - .01 * entropy + bc_kl_coef * bc_kl
            _optimize(actor_loss, model.actor, actor_optimizer)
            actor_steps += 1
            exact_kl = rollout_exact_kl(model, rows)
            kl_trace.append(exact_kl)
            if exact_kl > target_kl:
                stopped = True
                break
        if stopped:
            break
    # Actor gradients are irrelevant to value fitting and must not enter its clipping.
    actor_optimizer.zero_grad(set_to_none=True)
    for order in schedules['critic']:
        for offset in range(0, len(order), 256):
            group = [rows[i] for i in order[offset:offset + 256]]
            _, values = model(*model.prepare([r['observation'] for r in group]))
            returns = torch.tensor([r['return'] for r in group], device=device)
            value_loss = F.mse_loss(values, returns)
            _optimize(.5 * value_loss, value_module, critic_optimizer)
            critic_steps += 1
    return {'actor_optimizer_steps': actor_steps, 'critic_optimizer_steps': critic_steps,
            'actor_early_stopped': stopped, 'rollout_exact_old_kl': exact_kl,
            'actor_step_exact_kl': kl_trace,
            'schedule': schedule,
            'critic_final_minibatch_loss': float(value_loss.detach())}


def train_stopped_ppo(checkpoint: Path, output: Path, *, evaluate: Callable[[Path, int], float],
                      updates: int = 32, hands: int = 64, seed: int = 29,
                      device: str = 'cuda', identity: str = '', eval_every: int = 4,
                      min_updates: int = 8, patience: int = 4, min_delta: float = 20.,
                      actor_epochs: int = 4, critic_epochs: int = 4,
                      target_kl: float = .03, actor_lr: float = 3e-4,
                      critic_lr: float = 3e-4,
                      resource_check: Callable[[], None] | None = None) -> Path:
    """Resume joint training and immutable development-selection receipts separately.

    Evaluation callbacks return mean net/jang on the frozen development seeds.
    A crash after a joint checkpoint but before evaluation replays only evaluation.
    """
    if (updates <= 0 or hands <= 0 or not 0 <= seed < 500 or eval_every <= 0
            or min_updates < 0 or patience <= 0 or min_delta < 0
            or not math.isfinite(min_delta)
            or any(not math.isfinite(lr) or lr <= 0 for lr in (actor_lr, critic_lr))):
        raise ValueError('Invalid stopped PPO budget')
    determinism = configure_determinism(device, True)
    spec = training_spec(Ruleset())
    contract = {'version': 3, 'parent_sha256': fingerprint(checkpoint), 'updates': updates,
                'hands': hands, 'seed': seed, 'device': device, 'identity': identity,
                'eval_every': eval_every, 'min_updates': min_updates, 'patience': patience,
                'min_delta': min_delta, 'actor_epochs': actor_epochs,
                'critic_epochs': critic_epochs,
                'target_kl': target_kl, 'bc_kl_coef': .2,
                'actor_lr': actor_lr, 'critic_lr': critic_lr,
                'schedule_version': 1,
                'source_sha256': {name: fingerprint(Path(__file__).with_name(name))
                                  for name in ['ppo_stopped.py', 'asymmetric.py', 'net.py',
                                               'train.py', 'stopping.py']},
                'resource_checks': resource_check is not None,
                'determinism': determinism}
    if resource_check is not None:
        resource_check()
    actor, saved = load_checkpoint(checkpoint, spec, device)
    if saved['stage'] != 'bc' or actor.architecture != 'temporal':
        raise ValueError('Stopped PPO requires a temporal BC parent')
    critic, _ = load_checkpoint(checkpoint, spec, device)
    reference, _ = load_checkpoint(checkpoint, spec, device)
    reference.eval().requires_grad_(False)
    random.seed(seed)
    torch.manual_seed(seed)
    model = IndependentCritic(actor, critic).to(device)
    actor_optimizer = torch.optim.Adam([p for p in actor.parameters() if p.requires_grad],
                                       lr=actor_lr)
    critic_optimizer = torch.optim.Adam(
        [p for module in [model.critic, model.value_head]
         for p in module.parameters() if p.requires_grad], lr=critic_lr)
    output.mkdir(parents=True, exist_ok=True)
    history = []

    def check_learning_rates() -> None:
        for optimizer, lr in [(actor_optimizer, actor_lr), (critic_optimizer, critic_lr)]:
            if any(group['lr'] != lr for group in optimizer.param_groups):
                raise ValueError('Stopped PPO optimizer learning rate changed')

    def save_joint(index: int) -> None:
        with open_private_record(output / f'joint-{index:03}.pt') as handle:
            torch.save({'contract': contract, 'spec': spec, 'model': model.state_dict(),
                        'actor_optimizer': actor_optimizer.state_dict(),
                        'critic_optimizer': critic_optimizer.state_dict(), 'history': history,
                        'torch_rng': torch.get_rng_state(), 'python_rng': random.getstate(),
                        'device_rng': get_device_rng_state(device)}, handle.buffer)

    paths = sorted(output.glob('joint-*.pt'))
    if paths:
        if [p.name for p in paths] != [f'joint-{i:03}.pt' for i in range(len(paths))]:
            raise ValueError('Nonconsecutive stopped PPO checkpoints')
        payload = torch.load(paths[-1], map_location='cpu', weights_only=True)
        if payload.get('contract') != contract or payload['spec'] != spec:
            raise ValueError('Stopped PPO source, settings or checkpoint version changed')
        model.load_state_dict(payload['model'])
        actor_optimizer.load_state_dict(payload['actor_optimizer'])
        critic_optimizer.load_state_dict(payload['critic_optimizer'])
        check_learning_rates()
        torch.set_rng_state(payload['torch_rng'])
        random.setstate(payload['python_rng'])
        set_device_rng_state(device, payload['device_rng'])
        history = payload['history']
        if len(history) != len(paths) - 1:
            raise ValueError('Stopped PPO history/checkpoint mismatch')
    else:
        save_joint(0)

    def validation(index: int, stopping: Patience | None) -> Patience:
        receipt = output / f'selection-{index:03}.json'
        joint = output / f'joint-{index:03}.pt'
        if receipt.exists():
            item = json.loads(receipt.read_text())
            if item['contract'] != contract or item['joint_sha256'] != fingerprint(joint):
                raise ValueError('PPO development receipt identity changed')
            restored = Patience(**item['stopping'])
            expected = (Patience(**asdict(stopping)) if stopping else
                        Patience(patience, min_delta, -item['score'], -item['score']))
            if stopping:
                expected.observe(-item['score'], index)
            if asdict(expected) != asdict(restored):
                raise ValueError('PPO development stopping history mismatch')
            return restored
        export = output / f'eval-{index:03}.pt'
        # Export/evaluation must not perturb the training RNG stream.
        cpu_rng, py_rng = torch.get_rng_state(), random.getstate()
        device_rng = get_device_rng_state(device)
        try:
            if not export.exists():
                save_checkpoint(export, model.actor, spec, stage='ppo-actor',
                                optimizer=actor_optimizer,
                                progress={'joint_sha256': fingerprint(joint), 'contract': contract})
            else:
                _, exported = load_checkpoint(export, spec, device)
                if exported['progress'] != {
                        'joint_sha256': fingerprint(joint), 'contract': contract}:
                    raise ValueError('PPO evaluation export changed')
            score = float(evaluate(export, index))
            if not math.isfinite(score):
                raise RuntimeError('Nonfinite PPO development score')
        finally:
            torch.set_rng_state(cpu_rng)
            random.setstate(py_rng)
            set_device_rng_state(device, device_rng)
        if stopping is None:
            stopping = Patience(patience, min_delta, -score, -score)
        else:
            stopping.observe(-score, index)
        write_private_record(receipt, {'contract': contract, 'joint_sha256': fingerprint(joint),
                                      'score': score, 'stopping': asdict(stopping)})
        return stopping

    # Rebuild selection from immutable receipts; only the last completed point may be pending.
    stopping = None
    for index in [0, *range(eval_every, len(history) + 1, eval_every)]:
        if not (output / f'selection-{index:03}.json').exists() and index != len(history):
            raise ValueError('Missing earlier PPO development receipt')
        stopping = validation(index, stopping)
    while len(history) < updates and not (len(history) >= min_updates and stopping.stopped):
        if resource_check is not None:
            resource_check()
        update = len(history)
        model.train()
        print(json.dumps({'phase': 'ppo-rollout', 'update': update + 1}), flush=True)
        rows, metrics = collect_privileged(model, seed=seed, start=update * hands, hands=hands)
        metrics.update(update_independent(model, actor_optimizer, critic_optimizer, rows,
                       reference=VisibleReference(reference), actor_epochs=actor_epochs,
                       critic_epochs=critic_epochs, target_kl=target_kl,
                       schedule_seed=seed, schedule_update=update))
        model.eval()
        metrics.update(ppo_diagnostics(model, rows, VisibleReference(reference)))
        if not all(torch.isfinite(p).all() for p in model.parameters()):
            raise RuntimeError('Nonfinite stopped PPO weights')
        history.append({'update': update + 1, **metrics})
        save_joint(update + 1)
        if resource_check is not None:
            resource_check()
        print(json.dumps({'phase': 'ppo-update-complete', **history[-1]}), flush=True)
        if len(history) % eval_every == 0:
            stopping = validation(len(history), stopping)
    if len(history) % eval_every:
        stopping = validation(len(history), stopping)
    selected = output / f'joint-{stopping.best_index:03}.pt'
    complete = {'contract': contract, 'selected_update': stopping.best_index,
                'selected_joint_sha256': fingerprint(selected), 'updates': len(history),
                'hands': hands * len(history), 'stopping': asdict(stopping),
                'stop_reason': 'patience' if len(history) < updates else 'budget'}
    export = output / 'actor.pt'
    if export.exists():
        _, payload = load_checkpoint(export, spec, device)
        if payload['progress'] != complete:
            raise ValueError('Final stopped PPO export changed')
    else:
        payload = torch.load(selected, map_location='cpu', weights_only=True)
        model.load_state_dict(payload['model'])
        actor_optimizer.load_state_dict(payload['actor_optimizer'])
        check_learning_rates()
        save_checkpoint(export, model.actor, spec, stage='ppo-actor',
                        optimizer=actor_optimizer, progress=complete)
    return export
