"""Restore process-wide runtime flags after tests that request deterministic kernels."""
import os
import sys

import pytest


def _torch_flags(torch) -> tuple[bool, bool, bool]:
    if torch is None:
        return False, False, False  # PyTorch defaults before first import.
    return (torch.are_deterministic_algorithms_enabled(),
            torch.is_deterministic_algorithms_warn_only_enabled(),
            torch.backends.cudnn.benchmark)


@pytest.fixture(autouse=True)
def restore_torch_flags():
    """Undo global kernel flags set by training entry points, keeping test order irrelevant."""
    enabled, warn_only, benchmark = _torch_flags(sys.modules.get("torch"))
    yield
    torch = sys.modules.get("torch")
    if torch is not None:
        torch.use_deterministic_algorithms(enabled, warn_only=warn_only)
        torch.backends.cudnn.benchmark = benchmark


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
    """Require PyTorch and the CUDA workspace; restore_torch_flags undoes kernel flags."""
    pytest.importorskip("torch")
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
