"""Restore process-wide runtime flags after tests that request deterministic kernels."""
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def cuda_workspace_before_gpu_tests():
    previous = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CUBLAS_WORKSPACE_CONFIG", None)
        else:
            os.environ["CUBLAS_WORKSPACE_CONFIG"] = previous


@pytest.fixture
def deterministic_runtime(monkeypatch):
    torch = pytest.importorskip("torch")
    previous = torch.are_deterministic_algorithms_enabled()
    warn_only = torch.is_deterministic_algorithms_warn_only_enabled()
    benchmark = torch.backends.cudnn.benchmark
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    try:
        yield
    finally:
        torch.use_deterministic_algorithms(previous, warn_only=warn_only)
        torch.backends.cudnn.benchmark = benchmark
