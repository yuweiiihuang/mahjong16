"""Resumable, validation-selected continuation of an existing BC policy."""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import torch
from torch.nn import functional as F

from domain.rules.ruleset import Ruleset
from app.hand_store import write_private_record
from rl.env import training_spec
from rl.net import (PolicyValueNet, configure_determinism, load_checkpoint, save_checkpoint,
                    set_device_rng_state)
from rl.encoding import encode
from rl.dataset import bc_batches
from rl.stopping import Patience
from rl.train import _optimize, bc_metrics, dataset_batches


def fingerprint(path: Path) -> str:
    """Identify immutable checkpoint or data bytes without loading them into memory."""
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def data_manifest(path: Path, split: str) -> dict:
    """Bind every shard, rejecting empty input before training."""
    files = sorted(path.glob(f'{split}*.jsonl')) if path.is_dir() else [path]
    if not files:
        raise ValueError('No dataset files')
    return {str(p): fingerprint(p) for p in files}


def fresh_bc(train: Path, validation: Path, output: Path, *, seed: int = 29,
             epochs: int = 100, patience: int = 10, min_delta: float = .001,
             device: str = 'cpu', hidden: int = 128, identity: str = '',
             resource_check: Callable[[], None] | None = None,
             cache_dir: Path | None = None) -> Path:
    """Initialize a new temporal BC and Adam, then use validation-selected training."""
    determinism = configure_determinism(device, True)
    spec = training_spec(Ruleset())
    contract = {'seed': seed, 'hidden': hidden, 'device': device, 'identity': identity,
                'train': data_manifest(train, 'train'),
                'validation': data_manifest(validation, 'validation'),
                'determinism': determinism}
    output.mkdir(parents=True, exist_ok=True)
    initial = output / 'initial.pt'
    if initial.exists():
        _, saved = load_checkpoint(initial, spec, device)
        if saved['progress'].get('fresh_contract') != contract:
            raise ValueError('Fresh BC initialization contract changed')
    else:
        random.seed(seed)
        torch.manual_seed(seed)
        first = next(dataset_batches(train, spec, 'train', history=True), None)
        if first is None:
            raise ValueError('Fresh BC requires training choices')
        state, actions = encode(first[0]['observation'])
        model = PolicyValueNet(len(state), len(actions[0]), hidden=hidden,
                               architecture='temporal').to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
        save_checkpoint(initial, model, spec, stage='bc', optimizer=optimizer,
                        progress={'fresh_contract': contract})
    return continue_bc(initial, train, validation, output, epochs=epochs,
                       patience=patience, min_delta=min_delta, device=device, identity=identity,
                       resource_check=resource_check, cache_dir=cache_dir)


def continue_bc(checkpoint: Path, train: Path, validation: Path, output: Path, *,
                epochs: int = 10, patience: int = 3, min_delta: float = .001,
                device: str = 'cpu', identity: str = '',
                resource_check: Callable[[], None] | None = None,
                cache_dir: Path | None = None) -> Path:
    """Keep epoch zero eligible; resume complete epochs with Adam and device RNG.

    Patience counts validation checks; min_delta controls stopping only. Selection
    always retains the actual smallest held-out CE, independently of min_delta.
    """
    if epochs <= 0 or patience <= 0 or not 0 <= min_delta < float('inf'):
        raise ValueError('Invalid continuation budget')
    determinism = configure_determinism(device, True)
    spec = training_spec(Ruleset())
    contract = {'parent': str(checkpoint), 'parent_sha256': fingerprint(checkpoint),
                'train': data_manifest(train, 'train'),
                'validation': data_manifest(validation, 'validation'),
                'epochs': epochs, 'patience': patience, 'min_delta': min_delta,
                'device': device, 'determinism': determinism, 'identity': identity}
    if resource_check is not None:
        resource_check()
        contract['resource_checks'] = True
    # Validate shard ranges/contracts even when recovery has no remaining updates.
    for path, split in ((train, 'train'), (validation, 'validation')):
        if next(dataset_batches(path, spec, split, history=True), None) is None:
            raise ValueError('Dataset has no choices')
    output.mkdir(parents=True, exist_ok=True)
    paths = sorted(output.glob('epoch-*.pt'))
    if [p.name for p in paths] != [f'epoch-{i:03}.pt' for i in range(len(paths))]:
        raise ValueError('Non-consecutive continuation checkpoints')
    model, saved = load_checkpoint(paths[-1] if paths else checkpoint, spec, device)
    if not saved['stage'].startswith('bc') or saved.get('optimizer') is None:
        raise ValueError('Continuation requires a BC policy and Adam state')
    if saved.get('device') != device:
        raise ValueError('Continuation requires the same device for exact RNG recovery')
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    optimizer.load_state_dict(saved['optimizer'])
    torch.set_rng_state(saved['torch_rng'])
    random.setstate(saved['python_rng'])
    set_device_rng_state(device, saved.get('device_rng'))
    if paths:
        progress = saved['progress']
        if progress['continuation_contract'] != contract:
            raise ValueError('Continuation data, source or settings changed')
        history = progress['history']
        meaningful, stale = progress['meaningful_loss'], progress['stale']
    else:
        model.eval()
        history = [{'epoch': 0, 'validation': bc_metrics(
            model, validation, spec, 'validation', cache_dir=cache_dir)}]
        meaningful, stale = history[0]['validation']['all']['loss'], 0
        if not torch.isfinite(torch.tensor(meaningful)):
            raise RuntimeError('Non-finite initial validation loss')
        save_checkpoint(output / 'epoch-000.pt', model, spec, stage='bc', optimizer=optimizer,
                        progress={'continuation_contract': contract, 'history': history,
                                  'epoch': 0, 'meaningful_loss': meaningful, 'stale': stale})
    selected = min(history, key=lambda row: row['validation']['all']['loss'])
    stopping = Patience(patience, min_delta, meaningful,
                        selected['validation']['all']['loss'], selected['epoch'],
                        history[-1]['epoch'], stale)
    for epoch in range(len(history), epochs + 1):
        if stopping.stopped:
            break
        if resource_check is not None:
            resource_check()
        model.train()
        choices, steps = 0, 0
        for inputs, labels, _ in bc_batches(
                train, spec, 'train', history=model.architecture == 'temporal',
                device=device, cache_dir=cache_dir, shuffle=True):
            logits, _ = model(*inputs)
            _optimize(F.cross_entropy(logits, labels), model, optimizer)
            choices += len(labels)
            steps += 1
        model.eval()
        metrics = bc_metrics(model, validation, spec, 'validation', cache_dir=cache_dir)
        loss = metrics['all']['loss']
        if not torch.isfinite(torch.tensor(loss)):
            raise RuntimeError('Non-finite validation loss')
        stopping.observe(loss, epoch)
        meaningful, stale = stopping.anchor, stopping.stale
        history.append({'epoch': epoch, 'validation': metrics,
                        'choices': choices, 'optimizer_steps': steps})
        save_checkpoint(output / f'epoch-{epoch:03}.pt', model, spec, stage='bc',
                        optimizer=optimizer,
                        progress={'continuation_contract': contract, 'history': history,
                                  'epoch': epoch, 'meaningful_loss': meaningful, 'stale': stale})
        print(json.dumps({'phase': 'bc-epoch-complete', **history[-1], 'stale': stale}),
              flush=True)
        if resource_check is not None:
            resource_check()
    selected = min(history, key=lambda row: row['validation']['all']['loss'])['epoch']
    summary = {'contract': contract, 'completed_epochs': history[-1]['epoch'],
               'selected_epoch': selected, 'stopping': asdict(stopping),
               'optimizer_steps': sum(row.get('optimizer_steps', 0) for row in history),
               'stop_reason': 'budget' if history[-1]['epoch'] == epochs else 'patience'}
    receipt = output / 'training-summary.json'
    if receipt.exists():
        if json.loads(receipt.read_text()) != summary:
            raise ValueError('BC completion summary changed')
    else:
        write_private_record(receipt, summary)
    return output / f'epoch-{selected:03}.pt'
