"""Structured policy and actual-device contracts; GPU checks require device access."""
from copy import deepcopy

import pytest

torch = pytest.importorskip("torch")

from domain.rules.ruleset import Ruleset
from rl.env import HandEpisode, training_spec
from rl.history import DecisionHistory
from rl.net import PolicyValueNet, _board_tokens, batch, load_checkpoint, resolve_device
from rl.train import train_ppo, update_ppo


def test_board_tokens_preserve_tile_seat_and_hidden_meld_fields():
    obs = HandEpisode(0).current()
    obs.update(player=0, seat_winds=["E", "S", "W", "N"], hand=[3, 3], drawn=8,
               blocked_discards=[9], last_discard={"pid": 2, "tile": 12})
    obs["players"][2]["melds"] = [{"type": "PONG", "tiles": [17] * 3}]
    obs["players"][1]["melds"] = [{"type": "ANGANG", "tiles": [None] * 4}]
    states, _, _ = batch([obs])
    tiles, seats, global_state = _board_tokens(states)
    assert tiles.shape == (1, 34, 28)
    assert seats.shape == (1, 4, 17)
    assert global_state.shape == (1, 15)
    assert tiles[0, 3, 0] == 0.5
    assert tiles[0, 8, 1] == 0.25
    assert tiles[0, 9, 2] == 0.25
    assert tiles[0, 12, -1] == 0.25
    assert tiles[0, 17, 18] == 0.75  # Relative player 2, PONG kind.
    assert seats[0, 1, 15] == 1  # Relative player 1, concealed kong count.
    assert torch.count_nonzero(tiles[0, :, 15]) == 0  # Its hidden tiles stay absent.
    unique = torch.arange(1035, dtype=torch.float32)[None]
    regrouped = torch.cat([part.flatten() for part in _board_tokens(unique)])
    torch.testing.assert_close(regrouped.sort().values, unique.flatten())


def test_unavailable_mps_fails_explicitly_without_cpu_fallback(monkeypatch):
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="MPS is unavailable"):
        resolve_device("mps")


def test_unavailable_cuda_fails_explicitly_without_cpu_fallback(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="CUDA is unavailable"):
        resolve_device("cuda")


def test_determinism_is_opt_in_and_requires_cuda_startup_configuration(
        monkeypatch, deterministic_runtime):
    from rl.net import configure_determinism

    torch.use_deterministic_algorithms(False)
    monkeypatch.delenv("CUBLAS_WORKSPACE_CONFIG")
    assert configure_determinism("cpu") == {
        "enabled": False, "warn_only": False, "cublas_workspace_config": None}
    monkeypatch.setattr(torch.cuda, "is_initialized", lambda: True)
    with pytest.raises(RuntimeError, match="before initializing CUDA"):
        configure_determinism("cuda", True)
    assert not torch.are_deterministic_algorithms_enabled()
    monkeypatch.setattr(torch.cuda, "is_initialized", lambda: False)
    settings = configure_determinism("cuda", True)
    assert settings == {"enabled": True, "warn_only": False,
                        "cublas_workspace_config": ":4096:8"}
    assert torch.are_deterministic_algorithms_enabled()
    assert not torch.backends.cudnn.benchmark
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", "invalid")
    with pytest.raises(ValueError, match="CUBLAS_WORKSPACE_CONFIG"):
        configure_determinism("cuda", True)


def test_ppo_determinism_provenance_and_legacy_resume(tmp_path, monkeypatch,
                                                   deterministic_runtime):
    import rl.train as training
    from rl.net import save_checkpoint

    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(False)
    spec = training_spec(Ruleset())
    obs = HandEpisode(2).current()
    model = PolicyValueNet(1035, 82, hidden=16)
    initial = tmp_path / "bc.pt"
    save_checkpoint(initial, model, spec, stage="bc",
                    optimizer=torch.optim.Adam(model.parameters()), progress={})

    def rollout(actor, **kwargs):
        with torch.no_grad():
            logits, value = actor(*actor.prepare([obs]))
        return [{"observation": obs, "label": 0, "return": 1.,
                 "old_log_prob": float(logits.log_softmax(-1)[0, 0]),
                 "old_value": float(value[0])}], {
                     "hands": 1, "engine_steps": 1, "decisions": 1, "choices": 1}

    monkeypatch.setattr(training, "collect_rollout", rollout)
    first, resumed = tmp_path / "one.pt", tmp_path / "two.pt"
    train_ppo(initial, first, hands=1, deterministic=True)
    saved = torch.load(first, weights_only=True)
    assert saved["progress"]["settings"]["determinism"]["enabled"] is True
    torch.use_deterministic_algorithms(False)
    with pytest.raises(ValueError, match="determinism"):
        train_ppo(first, resumed, hands=1)
    train_ppo(first, resumed, hands=1, deterministic=True)
    assert load_checkpoint(resumed, spec)[1]["progress"]["completed"] == 2

    # Actual old nondeterministic PPO payloads have no determinism setting.
    torch.use_deterministic_algorithms(False)
    legacy_new = tmp_path / "legacy-new.pt"
    train_ppo(initial, legacy_new, hands=1)
    legacy = torch.load(legacy_new, weights_only=True)
    del legacy["progress"]["settings"]["determinism"]
    legacy_path = tmp_path / "legacy.pt"
    torch.save(legacy, legacy_path)
    train_ppo(legacy_path, tmp_path / "legacy-resumed.pt", hands=1)


@pytest.mark.parametrize("device", [
    pytest.param("mps", marks=pytest.mark.skipif(
        not torch.backends.mps.is_available(), reason="MPS requires GPU access")),
    pytest.param("cuda", marks=pytest.mark.skipif(
        not torch.cuda.is_available(), reason="CUDA requires GPU access")),
])
@pytest.mark.parametrize("architecture", ["mlp", "transformer", "hierarchical", "temporal"])
def test_gpu_matches_cpu_and_supports_update_checkpoint_and_resume(tmp_path, architecture, device):
    torch.set_num_threads(1)
    torch.manual_seed(7)
    obs = HandEpisode(2).current()
    obs["legal_actions"] = obs["legal_actions"][:2]
    if architecture == "temporal":
        history = DecisionHistory()
        history.append(obs, obs["legal_actions"][0])
        obs = history.observe(obs)
    state, actions, _ = batch([obs])
    cpu = PolicyValueNet(state.shape[-1], actions.shape[-1], hidden=16,
                         architecture=architecture)
    gpu = deepcopy(cpu).to(device)
    with torch.no_grad():
        cpu_logits, cpu_value = cpu(*cpu.prepare([obs]))
        gpu_logits, gpu_value = gpu(*gpu.prepare([obs]))
    torch.testing.assert_close(cpu_logits, gpu_logits.cpu(), atol=2e-4, rtol=2e-4)
    torch.testing.assert_close(cpu_value, gpu_value.cpu(), atol=2e-4, rtol=2e-4)
    rows = [{"observation": obs, "label": 0,
             "old_log_prob": float(gpu_logits.log_softmax(-1)[0, 0]),
             "old_value": float(gpu_value[0]), "return": float(gpu_value[0]) + 1}]
    optimizer = torch.optim.Adam(gpu.parameters(), lr=3e-4)
    metrics = update_ppo(gpu, optimizer, rows, epochs=1)
    assert all(torch.isfinite(torch.tensor(value)) for value in metrics.values())

    from rl.net import save_checkpoint
    path = tmp_path / f"{device}.pt"
    backend = torch.mps if device == "mps" else torch.cuda
    backend.manual_seed(11)
    spec = training_spec(Ruleset())
    save_checkpoint(path, gpu, spec, stage="ppo", optimizer=optimizer,
                    progress={"settings": {"hands": 1, "seed": 0}})
    loaded, saved = load_checkpoint(path, spec, device)
    assert next(loaded.parameters()).device.type == device
    assert saved["device"] == device and saved["device_rng"] is not None
    torch.testing.assert_close(loaded(*loaded.prepare([obs]))[0],
                               gpu(*gpu.prepare([obs]))[0])
    with pytest.raises(ValueError, match="same.*device"):
        train_ppo(path, tmp_path / "cross-device.pt", hands=1, device="cpu")
    expected = torch.rand(4, device=device).cpu()
    backend.set_rng_state(saved["device_rng"])
    torch.testing.assert_close(torch.rand(4, device=device).cpu(), expected, rtol=0, atol=0)
