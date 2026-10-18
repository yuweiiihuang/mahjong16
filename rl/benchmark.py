"""Compare CPU/MPS/CUDA minibatch updates and single-decision inference on real observations."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

import torch
from torch.nn import functional as F

from app.hand_store import write_private_record
from domain.rules.ruleset import Ruleset
from rl.env import training_spec
from rl.net import PolicyValueNet, batch, resolve_device
from rl.train import _optimize, dataset_batches


def _synchronize(device: str) -> None:
    if device in ("mps", "cuda"):
        (torch.mps if device == "mps" else torch.cuda).synchronize()


def _measure(operation, device: str, steps: int, repeats: int) -> dict:
    for _ in range(3):
        operation()
    seconds = []
    for _ in range(repeats):
        _synchronize(device)
        began = perf_counter()
        for _ in range(steps):
            operation()
        _synchronize(device)
        seconds.append((perf_counter() - began) / steps)
    return {"median_seconds": median(seconds), "seconds_per_step": seconds}


def benchmark(dataset: Path, *, steps: int = 10, repeats: int = 3,
              sizes: list[int] | None = None, devices: list[str] | None = None,
              architectures: list[str] | None = None) -> dict:
    """Use paired FP32 weights/data; separate prepared kernels from encoding and transfers."""
    sizes = [32, 256] if sizes is None else sizes
    if steps <= 0 or repeats <= 0 or not sizes or any(size <= 0 for size in sizes):
        raise ValueError("Benchmark sizes, steps and repeats must be positive")
    if devices is None:
        devices = ["cpu"]
        if torch.backends.mps.is_available():
            devices.append("mps")
        if torch.cuda.is_available():
            devices.append("cuda")
    architectures = (["mlp", "transformer", "hierarchical", "temporal"]
                     if architectures is None else architectures)
    if not devices or len(set(devices)) != len(devices):
        raise ValueError("Benchmark needs distinct devices")
    if (not architectures or len(set(architectures)) != len(architectures)
            or set(architectures) - {"mlp", "transformer", "hierarchical", "temporal"}):
        raise ValueError("Invalid benchmark architectures")
    for device in devices:
        resolve_device(device)
    rows = next(dataset_batches(dataset, training_spec(Ruleset()), "train", size=max(sizes),
                                history="temporal" in architectures), [])
    if len(rows) < max(sizes):
        raise ValueError("Dataset has too few choice decisions for this benchmark")
    states, actions, _ = batch([rows[0]["observation"]])
    results = []
    for architecture in architectures:
        torch.manual_seed(0)
        initial = PolicyValueNet(states.shape[-1], actions.shape[-1], architecture=architecture)
        initial.eval()
        with torch.no_grad():
            obs = [r["observation"] for r in rows[:4]]
            cpu = initial(*initial.prepare(obs))
            for device in devices:
                other = deepcopy(initial).to(device)
                actual = other(*other.prepare(obs))
                for expected, value in zip(cpu, actual):
                    torch.testing.assert_close(value.cpu(), expected, atol=5e-4, rtol=5e-4)
                del other, actual
        for size in sizes:
            observations = [r["observation"] for r in rows[:size]]
            for device in devices:
                for include_encoding in (False, True):
                    model = deepcopy(initial).to(device).train()
                    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
                    packed = model.prepare(observations)
                    labels = torch.tensor([r["label"] for r in rows[:size]], device=device)

                    def update():
                        inputs = model.prepare(observations) if include_encoding else packed
                        logits, _ = model(*inputs)
                        _optimize(F.cross_entropy(logits, labels), model, optimizer)

                    measured = _measure(update, device, steps, repeats)
                    row = {"architecture": architecture, "device": device, "batch_size": size,
                           "operation": "bc_with_encoding" if include_encoding else "bc_prepared",
                           "parameters": sum(p.numel() for p in initial.parameters()),
                           "max_candidates": packed[1].shape[1], **measured}
                    results.append(row)
                    print(json.dumps(row), flush=True)

        for device in devices:
            model = deepcopy(initial).to(device).eval()
            measured = _measure(lambda: model.choose(rows[0]["observation"]),
                                device, steps, repeats)
            row = {"architecture": architecture, "device": device, "batch_size": 1,
                   "operation": "choose_with_encoding", **measured}
            results.append(row)
            print(json.dumps(row), flush=True)
    with dataset.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return {"benchmark_version": 2, "torch": str(torch.__version__), "dtype": "float32",
            "cpu_threads": torch.get_num_threads(), "warmup_steps": 3,
            "steps": steps, "repeats": repeats, "dataset": str(dataset),
            "devices": devices, "architectures": architectures,
            "dataset_sha256": digest, "results": results,
            "limits": "Minibatch and choose timings exclude disk IO, engine and Greedy opponents"}


def main() -> None:
    """Write an owner-only benchmark receipt, without replacing existing output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--sizes", type=int, nargs="+", default=[32, 256])
    parser.add_argument("--devices", nargs="+", choices=("cpu", "mps", "cuda"),
                        help="Default: CPU and available accelerators; runs sequentially")
    parser.add_argument("--architectures", nargs="+",
                        choices=("mlp", "transformer", "hierarchical", "temporal"))
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = vars(parser.parse_args())
    path = args.pop("output")
    threads = args.pop("threads")
    if path.exists():
        raise FileExistsError(path)
    if threads <= 0:
        raise ValueError("CPU threads must be positive")
    torch.set_num_threads(threads)
    write_private_record(path, benchmark(**args))


if __name__ == "__main__":
    main()
