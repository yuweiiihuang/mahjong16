"""Validated JSONL decisions and optional, content-addressed CPU tensor caches."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import random
import tempfile
from typing import Iterator

import torch

from app.hand_store import open_private_record, private_record_path, write_private_record
from rl.encoding import ENCODING_VERSION, encode
from rl.history import DecisionHistory
from rl.net import batch
from rl.selfplay import hand_seed


def _shards(path: Path, split: str) -> list[Path]:
    if not path.is_dir():
        return [path]
    files = sorted(path.glob(f"{split}*.jsonl"))
    ranges = []
    for shard in files:
        with shard.open() as handle:
            header = json.loads(next(handle))
        start, hands = header["start"], header["hands"]
        if type(start) is not int or type(hands) is not int or hands <= 0:
            raise ValueError("Invalid dataset seed range")
        ranges.append((start, start + hands))
    ordered = sorted(ranges)
    if not files or any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Empty or overlapping dataset shards")
    return files


def dataset_batches(path: Path, spec: dict, split: str,
                    size: int = 256, *, history: bool = False) -> Iterator[list[dict]]:
    """Stream choice decisions and reject labels or seeds outside the declared split."""
    if size <= 0:
        raise ValueError("Batch size must be positive")
    if path.is_dir():
        for shard in _shards(path, split):
            yield from dataset_batches(shard, spec, split, size, history=history)
        return
    with path.open() as handle:
        header = json.loads(next(handle))
        if (header.get("dataset_version") != 1 or header.get("spec") != spec
                or header.get("encoding_version") != ENCODING_VERSION
                or header.get("split") != split):
            raise ValueError("Dataset version, rules or split mismatch")
        start, hands = header["start"], header["hands"]
        if (type(start) is not int or type(hands) is not int or start < 0 or hands <= 0
                or start + hands > 500_000_000):
            raise ValueError("Invalid dataset seed range")
        first = hand_seed(split, start)
        last = hand_seed(split, start + hands - 1)
        rows = []
        memories = {}
        previous_seed, previous_seq = None, -1
        for line in handle:
            row = json.loads(line)
            obs, label = row["observation"], row["label"]
            if (type(row["seed"]) is not int or not first <= row["seed"] <= last
                    or type(label) is not int or not 0 <= label < len(obs["legal_actions"])):
                raise ValueError("Invalid dataset seed or candidate label")
            encode(obs)
            if history:
                seq = row.get("seq")
                if (type(seq) is not int or "decision_history" in obs
                        or (previous_seed is not None and row["seed"] < previous_seed)):
                    raise ValueError("History requires ordered, unmodified decision rows")
                if row["seed"] != previous_seed:
                    memories = {}
                    previous_seq = -1
                if seq != previous_seq + 1:
                    raise ValueError("History requires complete consecutive decision rows")
                previous_seed, previous_seq = row["seed"], seq
                memory = memories.setdefault(obs["player"], DecisionHistory())
                row["observation"] = memory.observe(obs)
                executed = row.get("executed_action", obs["legal_actions"][label])
                if executed not in obs["legal_actions"]:
                    raise ValueError("Invalid executed action in dataset")
                memory.append(obs, executed)
            if len(obs["legal_actions"]) > 1:
                rows.append(row)
            if len(rows) == size:
                yield rows
                rows = []
        if rows:
            yield rows


def _digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _packed(rows: list[dict], history: bool) -> dict:
    return {'inputs': batch([r['observation'] for r in rows], history=history),
            'labels': torch.tensor([r['label'] for r in rows]),
            'groups': [(r['observation']['phase'],
                        r['observation']['legal_actions'][r['label']]['type']) for r in rows]}


def _cached(path: Path, spec: dict, split: str, size: int, history: bool,
            cache_dir: Path) -> Iterator[dict]:
    # Bind executable preprocessing as well as data; version constants alone can miss edits.
    contract = {'source_sha256': _digest(path), 'spec': spec, 'split': split,
                'size': size, 'history': history, 'torch': str(torch.__version__),
                'dtype': str(torch.get_default_dtype()),
                'code': {name: _digest(Path(__file__).with_name(name)) for name in
                         ('dataset.py', 'encoding.py', 'history.py', 'net.py', 'selfplay.py')}}
    identity = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    root = private_record_path(cache_dir)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / identity
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix='.building-', dir=root) as temporary:
            staging = Path(temporary)
            digests = []
            for index, rows in enumerate(dataset_batches(path, spec, split, size, history=history)):
                part = staging / f'{index:06}.pt'
                with open_private_record(part) as handle:
                    torch.save(_packed(rows, history), handle.buffer)
                digests.append(_digest(part))
            if _digest(path) != contract['source_sha256']:
                raise ValueError('Dataset changed while building tensor cache')
            write_private_record(staging / 'manifest.json',
                                 {'contract': contract, 'sha256': digests})
            try:
                os.rename(staging, target)
            except OSError:
                # Another complete builder may have won publication; verify its manifest below.
                if not (target / 'manifest.json').is_file():
                    raise
    manifest = json.loads((target / 'manifest.json').read_text())
    if manifest['contract'] != contract:
        raise ValueError('Tensor cache contract mismatch')
    expected = {f'{index:06}.pt' for index in range(len(manifest['sha256']))}
    if {p.name for p in target.glob('*.pt')} != expected:
        raise ValueError('Tensor cache shards missing or unexpected')
    for index, digest in enumerate(manifest['sha256']):
        part = target / f'{index:06}.pt'
        if _digest(part) != digest:
            raise ValueError('Tensor cache checksum mismatch')
        yield torch.load(part, map_location='cpu', weights_only=True, mmap=True)


def bc_batches(path: Path, spec: dict, split: str, *, history: bool = False,
               device: str = 'cpu', cache_dir: Path | None = None,
               shuffle: bool = False, size: int = 256) -> Iterator[tuple]:
    """Yield BC tensors and metric groups, preserving source batches and Python RNG.

    A cache is built only after validating the entire source shard. Forced decisions
    still contribute executed-action history before choice decisions are packed.
    """
    if size <= 0:
        raise ValueError('Batch size must be positive')
    if cache_dir is None:
        for rows in dataset_batches(path, spec, split, size, history=history):
            if shuffle:
                random.shuffle(rows)
            item = _packed(rows, history)
            yield (tuple(t.to(device) for t in item['inputs']),
                   item['labels'].to(device), item['groups'])
        return
    for shard in _shards(path, split):
        for item in _cached(shard, spec, split, size, history, cache_dir):
            inputs, labels, groups = item['inputs'], item['labels'], item['groups']
            if shuffle:
                order = list(range(len(labels)))
                random.shuffle(order)
                inputs = tuple(t[order] for t in inputs)
                labels = labels[order]
                groups = [groups[i] for i in order]
            yield tuple(t.to(device) for t in inputs), labels.to(device), groups
