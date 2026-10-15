"""Local BC and single-hand PPO training; no Web or production integration."""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import random
from time import perf_counter
from typing import Iterator

import torch
from torch.distributions import Categorical
from torch.nn import functional as F

from domain.rules.ruleset import Ruleset
from rl.encoding import ENCODING_VERSION, encode
from rl.env import LearnerEpisode, training_spec
from rl.net import PolicyValueNet, batch, load_checkpoint, save_checkpoint
from rl.selfplay import hand_seed


def dataset_batches(path: Path, spec: dict, split: str,
                    size: int = 256) -> Iterator[list[dict]]:
    """Stream choice decisions and reject labels or seeds outside the declared split."""
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
        for line in handle:
            row = json.loads(line)
            obs, label = row["observation"], row["label"]
            if (type(row["seed"]) is not int or not first <= row["seed"] <= last
                    or type(label) is not int or not 0 <= label < len(obs["legal_actions"])):
                raise ValueError("Invalid dataset seed or candidate label")
            encode(obs)
            if len(obs["legal_actions"]) > 1:
                rows.append(row)
            if len(rows) == size:
                yield rows
                rows = []
        if rows:
            yield rows


@torch.no_grad()
def bc_metrics(model: PolicyValueNet, path: Path, spec: dict, split: str) -> dict:
    """Report held-out choice accuracy by phase and teacher action, excluding forced moves."""
    groups = defaultdict(lambda: {"count": 0, "correct": 0, "loss": 0.0})
    for rows in dataset_batches(path, spec, split):
        logits, _ = model(*batch([r["observation"] for r in rows]))
        labels = torch.tensor([r["label"] for r in rows])
        losses = F.cross_entropy(logits, labels, reduction="none")
        predicted = logits.argmax(-1)
        for i, row in enumerate(rows):
            obs = row["observation"]
            kind = obs["legal_actions"][row["label"]]["type"]
            for key in ("all", obs["phase"], kind):
                group = groups[key]
                group["count"] += 1
                group["correct"] += int(predicted[i] == labels[i])
                group["loss"] += float(losses[i])
    if not groups["all"]["count"]:
        raise ValueError("Dataset has no choice decisions")
    return {key: {"count": g["count"], "accuracy": g["correct"] / g["count"],
                  "loss": g["loss"] / g["count"]} for key, g in groups.items()}


def _optimize(loss: torch.Tensor, model: PolicyValueNet,
              optimizer: torch.optim.Optimizer) -> None:
    if not torch.isfinite(loss):
        raise RuntimeError("Non-finite training loss")
    optimizer.zero_grad()
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 0.5, error_if_nonfinite=True)
    optimizer.step()


def train_bc(train: Path, validation: Path, output: Path, *, epochs: int = 10,
             seed: int = 0, rules: Ruleset | None = None) -> list[dict]:
    """Fit the teacher, selecting the best epoch using validation loss only."""
    if epochs <= 0 or output.exists():
        raise ValueError("Need positive epochs and a new output path")
    began = perf_counter()
    random.seed(seed)
    torch.manual_seed(seed)
    spec = training_spec(rules or Ruleset())
    manifests = {}
    for split, path in (("train", train), ("validation", validation)):
        with path.open() as handle:
            header = json.loads(next(handle))
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        manifests[split] = {"path": str(path), "header": header, "sha256": digest}
    first = next(dataset_batches(train, spec, "train"), None)
    if first is None:
        raise ValueError("Training data has no choices")
    state, actions = encode(first[0]["observation"])
    model = PolicyValueNet(len(state), len(actions[0]))
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    history = [{"epoch": 0, "validation": bc_metrics(model, validation, spec, "validation")}]
    best_loss = float("inf")
    best = None
    choices_seen = 0
    for epoch in range(1, epochs + 1):
        model.train()
        for rows in dataset_batches(train, spec, "train"):
            choices_seen += len(rows)
            random.shuffle(rows)
            logits, _ = model(*batch([r["observation"] for r in rows]))
            loss = F.cross_entropy(logits, torch.tensor([r["label"] for r in rows]))
            _optimize(loss, model, optimizer)
        model.eval()
        metrics = bc_metrics(model, validation, spec, "validation")
        record = {"epoch": epoch, "validation": metrics}
        history.append(record)
        print(json.dumps(record), flush=True)
        if metrics["all"]["loss"] < best_loss:
            best_loss = metrics["all"]["loss"]
            # Keep optimizer and RNG at the chosen epoch, not at the end of a later epoch.
            best = (copy.deepcopy(model.state_dict()), copy.deepcopy(optimizer.state_dict()),
                    torch.get_rng_state(), random.getstate(), epoch)
    model.load_state_dict(best[0])
    optimizer.load_state_dict(best[1])
    torch.set_rng_state(best[2])
    random.setstate(best[3])
    save_checkpoint(output, model, spec, stage="bc", optimizer=optimizer,
                    progress={"epoch": best[4], "seed": seed, "history": history,
                              "datasets": manifests, "choices_seen": choices_seen,
                              "training_seconds": perf_counter() - began})
    return history


@torch.no_grad()
def collect_rollout(model: PolicyValueNet, *, seed: int, start: int, hands: int,
                    rules: Ruleset) -> tuple[list[dict], dict]:
    """Collect complete learner trajectories; each transition keeps the same player."""
    rows = []
    began = perf_counter()
    payments = []
    engine_steps = 0
    if hands <= 0 or not 0 <= seed < 500 or start < 0 or start + hands > 1_000_000:
        raise ValueError("PPO seed stream exhausted or invalid rollout budget")
    for index in range(start, start + hands):
        # Reserve one million hands per run, above the demonstration namespace.
        stream_index = 500_000_000 + seed * 1_000_000 + index
        episode = LearnerEpisode(hand_seed("train", stream_index), index % 4, rules)
        hand_rows = []
        while (obs := episode.current()) is not None:
            logits, value = model(*batch([obs]))
            distribution = Categorical(logits=logits[0])
            action = distribution.sample()
            next_obs, reward, done = episode.step(obs["legal_actions"][int(action)])
            hand_rows.append({"observation": obs, "label": int(action),
                              "old_log_prob": float(distribution.log_prob(action)),
                              "old_value": float(value[0]), "reward": reward,
                              "terminated": done, "next_observation": next_obs})
        net = episode.payments()[episode.learner]
        for row in hand_rows:
            row["return"] = net / 100.0
        rows.extend(hand_rows)
        payments.append(net)
        engine_steps += episode.steps
    metrics = {"hands": hands, "engine_steps": engine_steps, "decisions": len(rows),
               "choices": sum(len(r["observation"]["legal_actions"]) > 1 for r in rows),
               "mean_payment": sum(payments) / hands,
               "rollout_seconds": perf_counter() - began}
    return rows, metrics


def update_ppo(model: PolicyValueNet, optimizer: torch.optim.Optimizer,
               rows: list[dict], epochs: int = 4) -> dict:
    """PPO-Clip with full-hand Monte Carlo returns and forced-action loss exclusion."""
    if not rows:
        raise ValueError("No learner decisions in rollout")
    advantages = torch.tensor([r["return"] - r["old_value"] for r in rows])
    choices = torch.tensor([len(r["observation"]["legal_actions"]) > 1 for r in rows])
    if choices.sum() > 1:
        sample = advantages[choices]
        advantages = (advantages - sample.mean()) / sample.std(unbiased=False).clamp_min(1e-8)
    order = list(range(len(rows)))
    metrics = {}
    for _ in range(epochs):
        random.shuffle(order)
        for offset in range(0, len(order), 256):
            indices = order[offset:offset + 256]
            group = [rows[i] for i in indices]
            logits, values = model(*batch([r["observation"] for r in group]))
            distribution = Categorical(logits=logits)
            labels = torch.tensor([r["label"] for r in group])
            log_ratio = distribution.log_prob(labels) - torch.tensor(
                [r["old_log_prob"] for r in group])
            ratio = log_ratio.exp()
            active = choices[indices]
            adv = advantages[indices]
            surrogate = torch.minimum(ratio * adv, ratio.clamp(0.8, 1.2) * adv)
            policy = -surrogate[active].mean() if active.any() else values.sum() * 0
            entropy = distribution.entropy()[active].mean() if active.any() else values.sum() * 0
            value_loss = F.mse_loss(values, torch.tensor([r["return"] for r in group]))
            loss = policy + 0.5 * value_loss - 0.01 * entropy
            kl = ((ratio - 1) - log_ratio)[active].mean() if active.any() else loss * 0
            metrics = {"loss": float(loss.detach()), "value_loss": float(value_loss.detach()),
                       "entropy": float(entropy.detach()), "kl": float(kl.detach())}
            if metrics["kl"] > 0.03:
                return metrics
            _optimize(loss, model, optimizer)
    return metrics


def train_ppo(checkpoint: Path, output: Path, *, updates: int = 1, hands: int = 8,
              seed: int = 0, rules: Ruleset | None = None) -> list[dict]:
    """Fine-tune BC or resume a complete PPO batch, preserving its random streams."""
    if updates <= 0 or hands <= 0 or not 0 <= seed < 500 or output.exists():
        raise ValueError("Invalid PPO budget, seed or output path")
    rules = rules or Ruleset()
    spec = training_spec(rules)
    model, saved = load_checkpoint(checkpoint, spec)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    settings = {"hands": hands, "seed": seed}
    if saved["stage"] == "ppo":
        if saved["progress"]["settings"] != settings:
            raise ValueError("Resume requires the same seed and hands per update")
        optimizer.load_state_dict(saved["optimizer"])
        torch.set_rng_state(saved["torch_rng"])
        random.setstate(saved["python_rng"])
        completed = saved["progress"]["completed"]
        cumulative = dict(saved["progress"]["cumulative"])
        bc_source = saved["progress"]["bc"]
    elif saved["stage"] == "bc":
        torch.manual_seed(seed)
        random.seed(seed)
        completed = 0
        cumulative = {key: 0 for key in
                      ("hands", "engine_steps", "decisions", "choices", "seconds")}
        bc_source = saved["progress"]
    else:
        raise ValueError("Checkpoint is neither BC nor PPO")
    history = []
    model.train()
    for update in range(completed, completed + updates):
        began = perf_counter()
        rows, metrics = collect_rollout(
            model, seed=seed, start=update * hands, hands=hands, rules=rules)
        metrics.update(update_ppo(model, optimizer, rows))
        metrics["update"] = update + 1
        metrics["seconds"] = perf_counter() - began
        for key in cumulative:
            cumulative[key] += metrics[key]
        history.append(metrics)
        print(json.dumps(metrics), flush=True)
    save_checkpoint(output, model, spec, stage="ppo", optimizer=optimizer,
                    progress={"completed": completed + updates, "settings": settings,
                              "history": history, "parent": str(checkpoint),
                              "cumulative": cumulative, "bc": bc_source})
    return history


def main() -> None:
    """Train on CPU first; outputs are new files, never in-place model replacements."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    bc = commands.add_parser("bc")
    bc.add_argument("train", type=Path)
    bc.add_argument("validation", type=Path)
    bc.add_argument("output", type=Path)
    bc.add_argument("--epochs", type=int, default=10)
    ppo = commands.add_parser("ppo")
    ppo.add_argument("checkpoint", type=Path)
    ppo.add_argument("output", type=Path)
    ppo.add_argument("--updates", type=int, default=1)
    ppo.add_argument("--hands", type=int, default=8)
    for command in (bc, ppo):
        command.add_argument("--seed", type=int, default=0)
    args = vars(parser.parse_args())
    mode = args.pop("mode")
    torch.set_num_threads(1)
    (train_bc if mode == "bc" else train_ppo)(**args)


if __name__ == "__main__":
    main()
