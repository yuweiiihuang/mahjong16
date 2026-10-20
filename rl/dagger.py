"""One learner-controlled DAgger collection round against fixed visible Greedy bots."""
from __future__ import annotations

import json
from pathlib import Path

import torch

from app.hand_store import open_private_record
from bots.greedy import GreedyBotStrategy
from domain.rules.ruleset import Ruleset
from rl.encoding import ENCODING_VERSION
from rl.env import LearnerEpisode, training_spec
from rl.finetune import fingerprint
from rl.history import DecisionHistory
from rl.net import load_checkpoint
from rl.selfplay import hand_seed


@torch.no_grad()
def collect_dagger(checkpoint: Path, output: Path, *, start: int, hands: int,
                   device: str = 'cpu') -> dict:
    """Query teacher before acting; histories retain executed learner actions, beta=0.

    Only actual learner observations are recorded. Forced moves remain in the data
    to reconstruct causal history, but are excluded from the supervised choice loss.
    """
    if start < 0 or hands <= 0 or start + hands > 500_000_000:
        raise ValueError('Invalid DAgger demonstration seed range')
    rules = Ruleset()
    spec = training_spec(rules)
    model, _ = load_checkpoint(checkpoint, spec, device)
    teacher = GreedyBotStrategy()
    counts = {'hands': hands, 'decisions': 0, 'choices': 0, 'disagreements': 0}
    with open_private_record(output) as handle:
        header = {'dataset_version': 1, 'encoding_version': ENCODING_VERSION, 'spec': spec,
                  'split': 'train', 'start': start, 'hands': hands,
                  'collection': 'dagger-beta0-learner-only-v1',
                  'behavior_sha256': fingerprint(checkpoint)}
        handle.write(json.dumps(header) + '\n')
        for index in range(start, start + hands):
            seed = hand_seed('train', index)
            episode = LearnerEpisode(seed, index % 4, rules)
            memory = DecisionHistory() if model.architecture == 'temporal' else None
            seq = 0
            while (obs := episode.current()) is not None:
                label = obs['legal_actions'].index(teacher.choose(obs))
                policy_obs = memory.observe(obs) if memory is not None else obs
                executed = model.choose(policy_obs)
                row = {'seed': seed, 'seq': seq, 'observation': obs, 'label': label,
                       'executed_action': executed}
                handle.write(json.dumps(row) + '\n')
                counts['decisions'] += 1
                counts['choices'] += len(obs['legal_actions']) > 1
                counts['disagreements'] += executed != obs['legal_actions'][label]
                if memory is not None:
                    memory.append(obs, executed)
                episode.step(executed)
                seq += 1
            episode.payments()
    return counts
