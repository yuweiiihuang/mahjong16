"""Benchmark device selection, asynchronous timing boundaries and real temporal packing."""
import json
from functools import wraps

import pytest

torch = pytest.importorskip("torch")

from rl.benchmark import _measure, benchmark
from rl.env import HandEpisode, training_spec
from domain.rules.ruleset import Ruleset


@pytest.mark.parametrize("device", ["cpu", "mps", "cuda"])
def test_measure_drains_warmup_and_synchronizes_both_timing_boundaries(monkeypatch, device):
    events = []
    monkeypatch.setattr(torch.mps, "synchronize", lambda: events.append("mps"))
    monkeypatch.setattr(torch.cuda, "synchronize", lambda: events.append("cuda"))
    measured = _measure(lambda: events.append("step"), device, steps=2, repeats=2)
    boundary = [] if device == "cpu" else [device]
    assert events == ["step"] * 3 + (boundary + ["step"] * 2 + boundary) * 2
    assert len(measured["seconds_per_step"]) == 2 and measured["median_seconds"] >= 0


def dataset(tmp_path):
    path = tmp_path / "train.jsonl"
    obs = HandEpisode(2).current()
    header = {"dataset_version": 1, "encoding_version": 1, "spec": training_spec(Ruleset()),
              "split": "train", "start": 2, "hands": 1}
    # Two consecutive visible decisions exercise a nonempty history in the temporal path.
    rows = [{"seed": 2, "seq": index, "observation": obs, "label": 0} for index in range(2)]
    path.write_text("\n".join(json.dumps(row) for row in [header, *rows]) + "\n")
    return path


def test_cpu_only_default_runs_temporal_with_production_history(tmp_path, monkeypatch):
    torch.set_num_threads(1)
    monkeypatch.setattr(torch.backends.mps, "is_available",
                        wraps(torch.backends.mps.is_available)(lambda: False))
    monkeypatch.setattr(torch.cuda, "is_available", wraps(torch.cuda.is_available)(lambda: False))
    from rl.net import PolicyValueNet
    original = PolicyValueNet.prepare
    lengths = []

    def prepare(self, observations):
        packed = original(self, observations)
        lengths.extend(packed[-1].tolist())
        return packed

    monkeypatch.setattr(PolicyValueNet, "prepare", prepare)
    result = benchmark(dataset(tmp_path), steps=1, repeats=1, sizes=[2],
                       architectures=["temporal"])
    assert result["benchmark_version"] == 2 and result["devices"] == ["cpu"]
    assert {r["operation"] for r in result["results"]} == {
        "bc_prepared", "bc_with_encoding", "choose_with_encoding"}
    assert 1 in lengths
    assert all(r["architecture"] == "temporal" for r in result["results"])


def test_explicit_unavailable_cuda_does_not_fall_back(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="CUDA is unavailable"):
        benchmark(tmp_path / "not-read.jsonl", devices=["cpu", "cuda"])


@pytest.mark.parametrize("options", [{"devices": []}, {"devices": ["cpu", "cpu"]},
                                    {"architectures": []}, {"architectures": ["unknown"]}])
def test_invalid_selection_is_rejected_before_dataset_read(tmp_path, options):
    with pytest.raises(ValueError):
        benchmark(tmp_path / "not-read.jsonl", **options)
