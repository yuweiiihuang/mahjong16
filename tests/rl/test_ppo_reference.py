"""Fixed-reference regularization, full-rollout diagnostics and resume provenance."""
from copy import deepcopy
import math

import pytest

torch = pytest.importorskip("torch")

from domain.rules.ruleset import Ruleset
from rl.env import HandEpisode, training_spec
from rl.net import PolicyValueNet, load_checkpoint, save_checkpoint
from rl.train import _policy_kl, ppo_diagnostics, train_ppo, update_ppo


def test_policy_kl_matches_bernoulli_value_with_zero_padded_mass():
    logits = torch.tensor([[math.log(.8), math.log(.2), -torch.inf]], requires_grad=True)
    reference = torch.tensor([[math.log(.5), math.log(.5), -torch.inf]])
    kl = _policy_kl(logits, reference)
    torch.testing.assert_close(kl, torch.tensor([.8 * math.log(1.6) + .2 * math.log(.4)]))
    kl.sum().backward()
    assert torch.isfinite(logits.grad).all() and logits.grad[0, 2] == 0


def test_bc_penalty_pulls_policy_towards_reference_without_updating_reference():
    torch.set_num_threads(1)
    torch.manual_seed(4)
    obs = HandEpisode(2).current()
    obs["legal_actions"] = obs["legal_actions"][:2]
    model = PolicyValueNet(1035, 82, hidden=16)
    reference = deepcopy(model).eval().requires_grad_(False)
    with torch.no_grad():
        reference.policy[-1].weight.mul_(20)
        logits, values = model(*model.prepare([obs]))
        target, _ = reference(*reference.prepare([obs]))
        before = float(_policy_kl(logits, target)[0])
    frozen = deepcopy(reference.state_dict())
    rows = [{"observation": obs, "label": 0,
             "old_log_prob": float(logits.log_softmax(-1)[0, 0]),
             "old_value": float(values[0]), "return": float(values[0])}]
    metrics = update_ppo(model, torch.optim.SGD(model.parameters(), lr=.05), rows,
                         epochs=1, reference=reference, bc_kl_coef=10)
    with torch.no_grad():
        assert float(_policy_kl(model(*model.prepare([obs]))[0], target)[0]) < before
    assert metrics["optimizer_steps"] == 1 and not metrics["early_stopped"]
    for name, value in reference.state_dict().items():
        torch.testing.assert_close(value, frozen[name], rtol=0, atol=0)
    assert all(p.grad is None for p in reference.parameters())
    with pytest.raises(ValueError, match="separate fixed"):
        update_ppo(model, torch.optim.SGD(model.parameters(), lr=.05), rows, bc_kl_coef=.2)


def test_early_stop_counts_zero_steps_and_diagnostics_cover_all_rollout_states():
    torch.set_num_threads(1)
    obs = HandEpisode(2).current()
    obs["legal_actions"] = obs["legal_actions"][:2]
    model = PolicyValueNet(1035, 82, hidden=16)
    with torch.no_grad():
        logits, value = model(*model.prepare([obs]))
    old = deepcopy(model.state_dict())
    row = {"observation": obs, "label": 0,
           "old_log_prob": float(logits.log_softmax(-1)[0, 0]) + 3,
           "old_value": float(value[0]), "return": -1.0}
    metrics = update_ppo(model, torch.optim.Adam(model.parameters()), [row])
    assert metrics["early_stopped"] and metrics["optimizer_steps"] == 0
    for name, actual in model.state_dict().items():
        torch.testing.assert_close(actual, old[name], rtol=0, atol=0)
    # Cross a minibatch boundary; all states must contribute, not just the last row.
    rows = [{**row, "return": float(i % 2)} for i in range(257)]
    rows[-1]["old_log_prob"] -= 3
    d = ppo_diagnostics(model, rows, deepcopy(model))
    assert d["rollout_policy_kl"] == pytest.approx((math.exp(-3) - 1 + 3) * 256 / 257)
    assert d["rollout_bc_kl"] == pytest.approx(0, abs=1e-7)
    assert d["critic_explained_variance_after"] == pytest.approx(0, abs=1e-6)
    assert ppo_diagnostics(model, [row])["critic_explained_variance_after"] is None


@pytest.mark.parametrize("device", ["cpu", pytest.param("mps", marks=pytest.mark.skipif(
    not torch.backends.mps.is_available(), reason="MPS requires GPU access")),
    pytest.param("cuda", marks=pytest.mark.skipif(
        not torch.cuda.is_available(), reason="CUDA requires GPU access"))])
def test_kl_resume_preserves_reference_rng_and_rejects_changed_settings(
        tmp_path, monkeypatch, device, deterministic_runtime):
    import rl.train as training

    torch.set_num_threads(1)
    torch.manual_seed(7)
    model = PolicyValueNet(1035, 82, hidden=16, architecture="temporal").to(device)
    spec = training_spec(Ruleset())
    initial, full, first, resumed = [tmp_path / f"{n}.pt"
                                    for n in ("bc", "full", "one", "two")]
    save_checkpoint(initial, model, spec, stage="bc",
                    optimizer=torch.optim.Adam(model.parameters()), progress={})
    obs = HandEpisode(2).current()
    obs["legal_actions"] = obs["legal_actions"][:2]

    def rollout(model, **_kwargs):
        with torch.no_grad():
            logits, value = model(*model.prepare([obs]))
        label = torch.distributions.Categorical(logits=logits[0]).sample()
        return [{"observation": obs, "label": int(label), "return": 1.,
                 "old_value": float(value[0]),
                 "old_log_prob": float(logits.log_softmax(-1)[0, label])}], {
                     "hands": 1, "engine_steps": 1, "decisions": 1, "choices": 1}

    monkeypatch.setattr(training, "collect_rollout", rollout)
    train_ppo(initial, full, updates=2, hands=1, device=device, bc_kl_coef=.2,
              deterministic=device == "cuda")
    train_ppo(initial, first, updates=1, hands=1, device=device, bc_kl_coef=.2,
              deterministic=device == "cuda")
    train_ppo(first, resumed, updates=1, hands=1, device=device, bc_kl_coef=.2,
              deterministic=device == "cuda")
    a, sa = load_checkpoint(full, spec)
    b, sb = load_checkpoint(resumed, spec)
    assert sa["progress"]["bc_reference"] == sb["progress"]["bc_reference"]
    assert sa["progress"]["settings"] == sb["progress"]["settings"]
    for name, v in a.state_dict().items():
        tol = 2e-5 if device == "mps" else 0
        torch.testing.assert_close(v, b.state_dict()[name], rtol=tol, atol=tol)
    torch.testing.assert_close(sa["torch_rng"], sb["torch_rng"], rtol=0, atol=0)
    assert sa["python_rng"] == sb["python_rng"]
    if device in ("mps", "cuda"):
        torch.testing.assert_close(sa["device_rng"], sb["device_rng"], rtol=0, atol=0)
    with pytest.raises(ValueError, match="reference/KL"):
        train_ppo(first, tmp_path / "wrong.pt", hands=1, device=device, bc_kl_coef=0)
    changed = torch.load(initial, weights_only=True)
    changed["progress"]["changed"] = True
    torch.save(changed, initial)
    with pytest.raises(ValueError, match="reference/KL"):
        train_ppo(first, tmp_path / "changed.pt", hands=1, device=device, bc_kl_coef=.2,
              deterministic=device == "cuda")
