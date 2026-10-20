"""Independent value network with decision-time opponent hand counts; actor stays visible."""
from __future__ import annotations

import json
import random
from pathlib import Path

import torch
from torch import nn

from domain.gameplay.game_env import MahjongEnvironment
from rl.env import LearnerEpisode
from rl.net import PolicyValueNet
from rl.history import DecisionHistory
from rl.selfplay import hand_seed
from torch.distributions import Categorical

def opponent_hands(env: MahjongEnvironment, learner: int) -> list[float]:
    """Copy current concealed tiles in next/opposite/previous relative seat order."""
    counts = [[0.] * 34 for _ in range(3)]
    for relative in range(1, 4):
        player = env.players[(learner + relative) % 4]
        concealed = [*player.hand, *([] if player.drawn is None else [player.drawn])]
        for tile in concealed:
            if not 0 <= tile < 34:
                raise ValueError("Unreplaced flower in current concealed hand")
            counts[relative - 1][tile] += .25
    return [x for seat in counts for x in seat]


class IndependentCritic(nn.Module):
    """Disjoint visible actor; equal-sized visible/privileged history critics."""
    def __init__(self, actor: PolicyValueNet, critic: PolicyValueNet,
                 privileged: bool = True) -> None:
        super().__init__()
        self.actor, self.critic = actor, critic
        self.privileged = privileged
        self.architecture = actor.architecture
        self.actor.value.requires_grad_(False)
        for name in ('action', 'query_norm', 'attention', 'action_ff', 'policy', 'action_type'):
            getattr(self.critic, name).requires_grad_(False)
        old = critic.value
        hidden = actor.dimensions[2]
        self.value_head = nn.Sequential(nn.Linear(hidden + 102, hidden), nn.ReLU(),
                                        nn.Linear(hidden, 1)).to(next(actor.parameters()).device)
        with torch.no_grad():
            self.value_head[0].weight.zero_()
            self.value_head[0].weight[:, :hidden].copy_(old[0].weight)
            self.value_head[0].bias.copy_(old[0].bias)
            self.value_head[2].load_state_dict(old[2].state_dict())
        self.critic.value = nn.Identity()
        assert not ({p.data_ptr() for p in actor.parameters()}
                    & {p.data_ptr() for p in critic.parameters()})

    def prepare(self, observations: list[dict]) -> tuple:
        """Remove privileged fields before packing actor and critic visible inputs."""
        visible = [{k: v for k, v in obs.items() if k != 'critic_hand_counts'}
                   for obs in observations]
        inputs = self.actor.prepare(visible)
        values = []
        for obs in observations:
            if self.privileged and 'critic_hand_counts' not in obs:
                raise ValueError("Missing decision-time critic snapshot")
            extra = obs.get('critic_hand_counts', [0.] * 102) if self.privileged else [0.] * 102
            if len(extra) != 102 or any(not 0 <= x <= 1 for x in extra):
                raise ValueError("Invalid concealed-tile snapshot")
            values.append(extra)
        return inputs + (torch.tensor(values, device=inputs[0].device),)

    def forward(self, *inputs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Evaluate disjoint actor and critic; only the value head sees hidden counts."""
        visible, extra = inputs[:-1], inputs[-1]
        logits, _ = self.actor(*visible)
        _, hidden = self.critic(*visible)
        value = self.value_head(torch.cat((hidden, extra), dim=-1)).squeeze(-1)
        return logits, value


class VisibleReference(nn.Module):
    """The BC regularizer receives only the original packed visible tensors."""
    def __init__(self, actor: PolicyValueNet) -> None:
        super().__init__()
        self.actor = actor

    def forward(self, *inputs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Strip the critic-only last tensor for BC KL regularization."""
        return self.actor(*inputs[:-1])



@torch.no_grad()
def collect_privileged(model: IndependentCritic, *, seed: int, start: int,
                       hands: int) -> tuple[list[dict], dict]:
    """Freeze concealed counts before each decision, excluding wall and future draws."""
    if hands <= 0 or not 0 <= seed < 500 or start < 0 or start + hands > 1_000_000:
        raise ValueError('Invalid privileged rollout budget')
    rows, payments = [], []
    for index in range(start, start + hands):
        stream = 500_000_000 + seed * 1_000_000 + index
        episode = LearnerEpisode(hand_seed('train', stream), index % 4)
        memory = DecisionHistory()
        hand_rows = []
        while (obs := episode.current()) is not None:
            obs = memory.observe(obs)
            obs['critic_hand_counts'] = opponent_hands(episode.env, episode.learner)
            logits, value = model(*model.prepare([obs]))
            distribution = Categorical(logits=logits[0])
            label = distribution.sample()
            action = obs['legal_actions'][int(label)]
            memory.append(obs, action)
            _, reward, done = episode.step(action)
            hand_rows.append({'observation': obs, 'label': int(label),
                              'old_log_prob': float(distribution.log_prob(label)),
                              'old_log_probs': distribution.logits.cpu().tolist(),
                              'old_value': float(value[0]), 'reward': reward, 'terminated': done})
        payment = episode.payments()[episode.learner]
        for row in hand_rows:
            row['return'] = payment / 100.
        rows.extend(hand_rows)
        payments.append(payment)
    return rows, {'hands': hands, 'decisions': len(rows),
                  'mean_payment': sum(payments) / hands}


def train_privileged_ppo(checkpoint: Path, output: Path, *, updates: int = 8,
                         hands: int = 64, seed: int = 19, device: str = 'cuda',
                         identity: str = '') -> Path:
    """Resume full joint actor/critic/Adam/RNG batches; export a visible actor only."""
    from app.hand_store import open_private_record
    from domain.rules.ruleset import Ruleset
    from rl.env import training_spec
    from rl.finetune import fingerprint
    from rl.net import (configure_determinism, get_device_rng_state, load_checkpoint,
                        save_checkpoint, set_device_rng_state)
    from rl.train import ppo_diagnostics, update_ppo

    if updates <= 0 or hands <= 0 or not 0 <= seed < 500:
        raise ValueError('Invalid PPO budget')
    determinism = configure_determinism(device, True)
    spec = training_spec(Ruleset())
    contract = {'parent_sha256': fingerprint(checkpoint), 'updates': updates,
                'hands': hands, 'seed': seed, 'device': device,
                'bc_kl_coef': .2, 'identity': identity, 'determinism': determinism}
    actor, saved = load_checkpoint(checkpoint, spec, device)
    if saved['stage'] != 'bc' or actor.architecture != 'temporal':
        raise ValueError('Privileged pilot requires a temporal BC checkpoint')
    critic, _ = load_checkpoint(checkpoint, spec, device)
    reference, _ = load_checkpoint(checkpoint, spec, device)
    reference.eval().requires_grad_(False)
    random.seed(seed)
    torch.manual_seed(seed)
    model = IndependentCritic(actor, critic, True).to(device)
    optimizer = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=3e-4)
    output.mkdir(parents=True, exist_ok=True)
    paths = sorted(output.glob('joint-*.pt'))
    if [p.name for p in paths] != [f'joint-{i:03}.pt' for i in range(1, len(paths) + 1)]:
        raise ValueError('Non-consecutive PPO checkpoints')
    history = []
    if paths:
        payload = torch.load(paths[-1], map_location='cpu', weights_only=True)
        if payload['contract'] != contract or payload['spec'] != spec:
            raise ValueError('PPO settings, source or parent changed')
        model.load_state_dict(payload['model'])
        optimizer.load_state_dict(payload['optimizer'])
        torch.set_rng_state(payload['torch_rng'])
        random.setstate(payload['python_rng'])
        set_device_rng_state(device, payload['device_rng'])
        history = payload['history']
        if len(history) != len(paths):
            raise ValueError('PPO progress mismatch')
    for update in range(len(history), updates):
        model.train()
        print(json.dumps({'phase': 'ppo-rollout', 'update': update + 1}), flush=True)
        rows, metrics = collect_privileged(model, seed=seed, start=update * hands, hands=hands)
        metrics.update(update_ppo(model, optimizer, rows,
                                  reference=VisibleReference(reference), bc_kl_coef=.2))
        model.eval()
        metrics.update(ppo_diagnostics(model, rows, VisibleReference(reference)))
        history.append({'update': update + 1, **metrics})
        if not all(torch.isfinite(p).all() for p in model.parameters()):
            raise RuntimeError('Non-finite PPO weights')
        with open_private_record(output / f'joint-{update + 1:03}.pt') as handle:
            torch.save({'contract': contract, 'spec': spec, 'model': model.state_dict(),
                        'optimizer': optimizer.state_dict(), 'history': history,
                        'torch_rng': torch.get_rng_state(), 'python_rng': random.getstate(),
                        'device_rng': get_device_rng_state(device)}, handle.buffer)
        print(json.dumps({'phase': 'ppo-update-complete', **history[-1]}), flush=True)
    export = output / 'actor.pt'
    last = output / f'joint-{updates:03}.pt'
    if export.exists():
        _, exported = load_checkpoint(export, spec, device)
        if exported['progress']['joint_sha256'] != fingerprint(last):
            raise ValueError('Export does not match final joint checkpoint')
    else:
        save_checkpoint(export, model.actor, spec, stage='ppo-actor', optimizer=optimizer,
                        progress={'joint_sha256': fingerprint(last), 'contract': contract,
                                  'history': history, 'completed': updates,
                                  'hands': updates * hands})
    return export
