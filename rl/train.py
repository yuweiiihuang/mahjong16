"""Local BC and single-hand PPO training; no Web or production integration."""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import hashlib
import json
import math
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
from rl.history import DecisionHistory
from rl.net import (PolicyValueNet, configure_determinism, get_device_rng_state, load_checkpoint,
                    resolve_device, save_checkpoint, set_device_rng_state)
from rl.selfplay import hand_seed


def dataset_batches(path: Path, spec: dict, split: str,
                    size: int = 256, *, history: bool = False) -> Iterator[list[dict]]:
    """Stream choice decisions and reject labels or seeds outside the declared split."""
    if path.is_dir():
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
        for shard in files:
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


@torch.no_grad()
def bc_metrics(model: PolicyValueNet, path: Path, spec: dict, split: str) -> dict:
    """Report held-out choice accuracy by phase and teacher action, excluding forced moves."""
    groups = defaultdict(lambda: {"count": 0, "correct": 0, "loss": 0.0})
    for rows in dataset_batches(path, spec, split, history=model.architecture == "temporal"):
        device = str(next(model.parameters()).device)
        logits, _ = model(*model.prepare([r["observation"] for r in rows]))
        labels = torch.tensor([r["label"] for r in rows], device=device)
        losses = F.cross_entropy(logits, labels, reduction="none")
        predicted = logits.argmax(-1).cpu().tolist()
        losses = losses.cpu().tolist()
        for i, row in enumerate(rows):
            obs = row["observation"]
            kind = obs["legal_actions"][row["label"]]["type"]
            for key in ("all", obs["phase"], kind):
                group = groups[key]
                group["count"] += 1
                group["correct"] += int(predicted[i] == row["label"])
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
             seed: int = 0, rules: Ruleset | None = None, device: str = "cpu",
             architecture: str = "mlp", deterministic: bool = False) -> list[dict]:
    """Fit the teacher, selecting the best epoch using validation loss only."""
    if epochs <= 0 or output.exists():
        raise ValueError("Need positive epochs and a new output path")
    target = resolve_device(device)
    determinism = configure_determinism(device, deterministic)
    began = perf_counter()
    random.seed(seed)
    torch.manual_seed(seed)
    if device == "mps":
        torch.mps.manual_seed(seed)
    spec = training_spec(rules or Ruleset())
    manifests = {}
    for split, path in (("train", train), ("validation", validation)):
        with path.open() as handle:
            header = json.loads(next(handle))
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        manifests[split] = {"path": str(path), "header": header, "sha256": digest}
    first = next(dataset_batches(train, spec, "train", history=architecture == "temporal"), None)
    if first is None:
        raise ValueError("Training data has no choices")
    state, actions = encode(first[0]["observation"])
    model = PolicyValueNet(len(state), len(actions[0]), architecture=architecture).to(target)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    history = [{"epoch": 0, "validation": bc_metrics(model, validation, spec, "validation")}]
    best_loss = float("inf")
    best = None
    choices_seen = 0
    for epoch in range(1, epochs + 1):
        model.train()
        for rows in dataset_batches(train, spec, "train", history=architecture == "temporal"):
            choices_seen += len(rows)
            random.shuffle(rows)
            logits, _ = model(*model.prepare([r["observation"] for r in rows]))
            loss = F.cross_entropy(logits, torch.tensor([r["label"] for r in rows], device=device))
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
                    torch.get_rng_state(), random.getstate(), epoch,
                    get_device_rng_state(device))
    model.load_state_dict(best[0])
    optimizer.load_state_dict(best[1])
    torch.set_rng_state(best[2])
    random.setstate(best[3])
    set_device_rng_state(device, best[5])
    save_checkpoint(output, model, spec, stage="bc", optimizer=optimizer,
                    progress={"epoch": best[4], "seed": seed, "history": history,
                              "datasets": manifests, "choices_seen": choices_seen,
                              "training_seconds": perf_counter() - began,
                              "determinism": determinism})
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
        memory = DecisionHistory() if model.architecture == "temporal" else None
        hand_rows = []
        while (obs := episode.current()) is not None:
            if memory is not None:
                obs = memory.observe(obs)
            logits, value = model(*model.prepare([obs]))
            distribution = Categorical(logits=logits[0])
            action = distribution.sample()
            if memory is not None:
                memory.append(obs, obs["legal_actions"][int(action)])
            next_obs, reward, done = episode.step(obs["legal_actions"][int(action)])
            if memory is not None and next_obs is not None:
                next_obs = memory.observe(next_obs)
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


def _policy_kl(logits: torch.Tensor, reference_logits: torch.Tensor) -> torch.Tensor:
    """KL(policy || BC) over complete legal candidates, excluding padded zero mass."""
    log_probs = logits.log_softmax(-1)
    reference_log_probs = reference_logits.log_softmax(-1)
    valid = torch.isfinite(logits)
    difference = (log_probs.masked_fill(~valid, 0)
                  - reference_log_probs.masked_fill(~valid, 0))
    return (log_probs.exp() * difference).sum(-1)


@torch.no_grad()
def ppo_diagnostics(model: PolicyValueNet, rows: list[dict],
                    reference: PolicyValueNet | None = None) -> dict:
    """Measure the final policy on all rollout states; value metrics include forced moves."""
    values, policy_kl, bc_kl, entropy = [], [], [], []
    for offset in range(0, len(rows), 256):
        group = rows[offset:offset + 256]
        inputs = model.prepare([r["observation"] for r in group])
        logits, predicted = model(*inputs)
        distribution = Categorical(logits=logits)
        labels = torch.tensor([r["label"] for r in group], device=logits.device)
        log_ratio = distribution.log_prob(labels) - torch.tensor(
            [r["old_log_prob"] for r in group], device=logits.device)
        active = torch.tensor([len(r["observation"]["legal_actions"]) > 1 for r in group],
                              device=logits.device)
        values.extend(predicted.cpu().tolist())
        policy_kl.extend(((log_ratio.exp() - 1) - log_ratio)[active].cpu().tolist())
        entropy.extend(distribution.entropy()[active].cpu().tolist())
        if reference is not None:
            reference_logits, _ = reference(*inputs)
            bc_kl.extend(_policy_kl(logits, reference_logits)[active].cpu().tolist())
    returns = torch.tensor([r["return"] for r in rows], dtype=torch.float64)
    before = torch.tensor([r["old_value"] for r in rows], dtype=torch.float64)
    after = torch.tensor(values, dtype=torch.float64)
    variance = returns.var(unbiased=False)

    def explained(predicted):
        return float(1 - (returns - predicted).var(unbiased=False) / variance) \
            if variance > 1e-12 else None

    return {"rollout_policy_kl": sum(policy_kl) / len(policy_kl) if policy_kl else 0.0,
            "rollout_bc_kl": sum(bc_kl) / len(bc_kl) if bc_kl else None,
            "rollout_entropy": sum(entropy) / len(entropy) if entropy else 0.0,
            "critic_explained_variance_before": explained(before),
            "critic_explained_variance_after": explained(after),
            "critic_rmse_after": float((returns - after).square().mean().sqrt()),
            "return_std": float(variance.sqrt())}


def update_ppo(model: PolicyValueNet, optimizer: torch.optim.Optimizer,
               rows: list[dict], epochs: int = 4, *,
               reference: PolicyValueNet | None = None, bc_kl_coef: float = 0.0) -> dict:
    """PPO-Clip with full-hand Monte Carlo returns and forced-action loss exclusion."""
    if not rows:
        raise ValueError("No learner decisions in rollout")
    if not math.isfinite(bc_kl_coef) or bc_kl_coef < 0:
        raise ValueError("BC KL coefficient must be finite and nonnegative")
    if bc_kl_coef and (reference is None or reference is model):
        raise ValueError("BC KL requires a separate fixed reference policy")
    device = str(next(model.parameters()).device)
    advantages = torch.tensor([r["return"] - r["old_value"] for r in rows], device=device)
    choices = torch.tensor([len(r["observation"]["legal_actions"]) > 1 for r in rows],
                           device=device)
    if choices.sum() > 1:
        sample = advantages[choices]
        advantages = (advantages - sample.mean()) / sample.std(unbiased=False).clamp_min(1e-8)
    order = list(range(len(rows)))
    metrics = {}
    steps = 0
    for _ in range(epochs):
        random.shuffle(order)
        for offset in range(0, len(order), 256):
            indices = order[offset:offset + 256]
            group = [rows[i] for i in indices]
            inputs = model.prepare([r["observation"] for r in group])
            logits, values = model(*inputs)
            distribution = Categorical(logits=logits)
            labels = torch.tensor([r["label"] for r in group], device=device)
            log_ratio = distribution.log_prob(labels) - torch.tensor(
                [r["old_log_prob"] for r in group], device=device)
            ratio = log_ratio.exp()
            active = choices[indices]
            adv = advantages[indices]
            surrogate = torch.minimum(ratio * adv, ratio.clamp(0.8, 1.2) * adv)
            policy = -surrogate[active].mean() if active.any() else values.sum() * 0
            entropy = distribution.entropy()[active].mean() if active.any() else values.sum() * 0
            returns = torch.tensor([r["return"] for r in group], device=device)
            value_loss = F.mse_loss(values, returns)
            bc_kl = values.sum() * 0
            if reference is not None:
                with torch.no_grad():
                    reference_logits, _ = reference(*inputs)
                divergence = _policy_kl(logits, reference_logits)
                bc_kl = divergence[active].mean() if active.any() else values.sum() * 0
            loss = policy + 0.5 * value_loss - 0.01 * entropy + bc_kl_coef * bc_kl
            kl = ((ratio - 1) - log_ratio)[active].mean() if active.any() else loss * 0
            metrics = {"loss": float(loss.detach()), "value_loss": float(value_loss.detach()),
                       "entropy": float(entropy.detach()), "kl": float(kl.detach()),
                       "bc_kl": float(bc_kl.detach()), "optimizer_steps": steps,
                       "early_stopped": False}
            if metrics["kl"] > 0.03:
                metrics["early_stopped"] = True
                return metrics
            _optimize(loss, model, optimizer)
            steps += 1
            metrics["optimizer_steps"] = steps
    return metrics


def train_ppo(checkpoint: Path, output: Path, *, updates: int = 1, hands: int = 8,
              seed: int = 0, rules: Ruleset | None = None,
              device: str = "cpu", bc_reference: Path | None = None,
              bc_kl_coef: float = 0.0, deterministic: bool = False) -> list[dict]:
    """Fine-tune BC or resume a complete PPO batch, preserving its random streams."""
    if updates <= 0 or hands <= 0 or not 0 <= seed < 500 or output.exists():
        raise ValueError("Invalid PPO budget, seed or output path")
    if not math.isfinite(bc_kl_coef) or bc_kl_coef < 0:
        raise ValueError("BC KL coefficient must be finite and nonnegative")
    rules = rules or Ruleset()
    spec = training_spec(rules)
    determinism = configure_determinism(device, deterministic)
    model, saved = load_checkpoint(checkpoint, spec, device)
    reference_info = saved["progress"].get("bc_reference") if saved["stage"] == "ppo" else None
    if bc_reference is None:
        if reference_info is not None:
            bc_reference = Path(reference_info["path"])
        elif bc_kl_coef and saved["stage"] == "bc":
            bc_reference = checkpoint
    reference = None
    if bc_reference is not None:
        reference, reference_saved = load_checkpoint(bc_reference, spec, device)
        if (reference_saved["stage"] != "bc" or reference.dimensions != model.dimensions
                or reference.architecture != model.architecture):
            raise ValueError("BC reference must be a matching BC checkpoint")
        reference.eval().requires_grad_(False)
        with bc_reference.open("rb") as handle:
            reference_info = {"path": str(bc_reference),
                              "sha256": hashlib.file_digest(handle, "sha256").hexdigest(),
                              "direction": "policy||bc"}
    elif bc_kl_coef:
        raise ValueError("BC KL requires an explicit BC reference for this checkpoint")
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    settings = {"hands": hands, "seed": seed, "bc_kl_coef": bc_kl_coef,
                "bc_reference_sha256": reference_info["sha256"] if reference_info else None,
                "determinism": determinism}
    if saved["stage"] == "ppo":
        old_settings = {"bc_kl_coef": 0.0, "bc_reference_sha256": None,
                        "determinism": {"enabled": False, "warn_only": False,
                                        "cublas_workspace_config": None},
                        **saved["progress"]["settings"]}
        if (old_settings != settings
                or saved.get("device", "cpu") != device):
            raise ValueError("Resume requires the same seed, hands, device, determinism "
                             "and BC reference/KL")
        optimizer.load_state_dict(saved["optimizer"])
        torch.set_rng_state(saved["torch_rng"])
        random.setstate(saved["python_rng"])
        set_device_rng_state(device, saved.get("device_rng"))
        completed = saved["progress"]["completed"]
        cumulative = dict(saved["progress"]["cumulative"])
        bc_source = saved["progress"]["bc"]
    elif saved["stage"] == "bc":
        torch.manual_seed(seed)
        random.seed(seed)
        if device == "mps":
            torch.mps.manual_seed(seed)
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
        metrics.update(update_ppo(model, optimizer, rows,
                                  reference=reference, bc_kl_coef=bc_kl_coef))
        metrics.update(ppo_diagnostics(model, rows, reference))
        metrics["update"] = update + 1
        metrics["seconds"] = perf_counter() - began
        for key in cumulative:
            cumulative[key] += metrics[key]
        history.append(metrics)
        print(json.dumps(metrics), flush=True)
    save_checkpoint(output, model, spec, stage="ppo", optimizer=optimizer,
                    progress={"completed": completed + updates, "settings": settings,
                              "history": history, "parent": str(checkpoint),
                              "cumulative": cumulative, "bc": bc_source,
                              "bc_reference": reference_info})
    return history


def main() -> None:
    """Train on an explicit device; outputs never replace existing models."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    bc = commands.add_parser("bc")
    bc.add_argument("train", type=Path)
    bc.add_argument("validation", type=Path)
    bc.add_argument("output", type=Path)
    bc.add_argument("--epochs", type=int, default=10)
    bc.add_argument("--architecture", choices=("mlp", "transformer", "hierarchical", "temporal"),
                    default="mlp")
    ppo = commands.add_parser("ppo")
    ppo.add_argument("checkpoint", type=Path)
    ppo.add_argument("output", type=Path)
    ppo.add_argument("--updates", type=int, default=1)
    ppo.add_argument("--hands", type=int, default=8)
    ppo.add_argument("--bc-reference", type=Path)
    ppo.add_argument("--bc-kl-coef", type=float, default=0.0)
    for command in (bc, ppo):
        command.add_argument("--deterministic", action="store_true",
                             help="Enable process-wide deterministic kernels; may be slower")
        command.add_argument("--seed", type=int, default=0)
        command.add_argument("--device", choices=("cpu", "mps", "cuda"), default="cpu")
    args = vars(parser.parse_args())
    mode = args.pop("mode")
    torch.set_num_threads(1)
    (train_bc if mode == "bc" else train_ppo)(**args)


if __name__ == "__main__":
    main()
