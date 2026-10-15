"""Optional-PyTorch tests for learning, artifact safety and policy update semantics."""
from copy import deepcopy
import json

import pytest

torch = pytest.importorskip("torch")
from torch.distributions import Categorical

from domain.rules.ruleset import Ruleset
from rl.env import HandEpisode, training_spec
from rl.net import PolicyValueNet, batch, load_checkpoint, save_checkpoint
from rl.selfplay import generate
from rl.train import bc_metrics, dataset_batches, train_bc, train_ppo, update_ppo


def make_model(obs):
    state, actions, _ = batch([obs])
    return PolicyValueNet(state.shape[-1], actions.shape[-1], hidden=16)


def test_padding_is_impossible_and_candidate_permutation_preserves_probabilities():
    obs = HandEpisode(2).current()
    reversed_obs = deepcopy(obs)
    reversed_obs["legal_actions"].reverse()
    forced = deepcopy(obs)
    forced["legal_actions"] = obs["legal_actions"][:1]
    model = make_model(obs)
    logits, _ = model(*batch([obs, reversed_obs, forced]))
    probs = logits.softmax(-1)
    torch.testing.assert_close(probs[0], probs[1].flip(0))
    assert probs[2, 0] == 1
    assert torch.count_nonzero(probs[2, 1:]) == 0
    assert model.choose(obs) in obs["legal_actions"]


def test_checkpoint_refuses_overwrite_and_incompatible_rules(tmp_path):
    obs = HandEpisode(0).current()
    model = make_model(obs)
    optimizer = torch.optim.Adam(model.parameters())
    spec = training_spec(Ruleset())
    path = tmp_path / "model.pt"
    save_checkpoint(path, model, spec, stage="bc", optimizer=optimizer, progress={})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_checkpoint(path, model, spec, stage="bc", optimizer=optimizer, progress={})
    assert path.read_bytes() == before
    assert path.stat().st_mode & 0o777 == 0o600
    loaded, _ = load_checkpoint(path, spec)
    torch.testing.assert_close(model(*batch([obs]))[0], loaded(*batch([obs]))[0])
    with pytest.raises(ValueError, match="match"):
        load_checkpoint(path, {**spec, "view_version": 999})


def test_ppo_increases_probability_of_advantaged_action_and_ignores_forced_policy_loss():
    torch.set_num_threads(1)
    torch.manual_seed(0)
    obs = HandEpisode(2).current()
    obs["legal_actions"] = obs["legal_actions"][:2]
    model = make_model(obs)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    with torch.no_grad():
        logits, values = model(*batch([obs]))
        probability = float(logits.softmax(-1)[0, 0])
        old_log = float(Categorical(logits=logits).log_prob(torch.tensor([0]))[0])
    rows = [{"observation": obs, "label": 0, "old_log_prob": old_log,
             "old_value": float(values[0]), "return": float(values[0]) + 1}]
    metrics = update_ppo(model, optimizer, rows, epochs=1)
    with torch.no_grad():
        assert float(model(*batch([obs]))[0].softmax(-1)[0, 0]) > probability
    assert all(torch.isfinite(torch.tensor(v)) for v in metrics.values())
    forced = deepcopy(obs)
    forced["legal_actions"] = obs["legal_actions"][:1]
    before = deepcopy(model.policy.state_dict())
    forced_rows = [{"observation": forced, "label": 0, "old_log_prob": 0,
                    "old_value": 0, "return": 1}]
    # A fresh optimizer excludes momentum from the previous policy update.
    fresh = torch.optim.Adam(model.parameters(), lr=0.01)
    update_ppo(model, fresh, forced_rows, epochs=1)
    for key, value in model.policy.state_dict().items():
        torch.testing.assert_close(value, before[key])


def test_bc_reduces_teacher_loss_and_rejects_split_leakage(tmp_path):
    torch.set_num_threads(1)
    obs = HandEpisode(2).current()
    spec = training_spec(Ruleset())
    paths = {}
    for split, seed in (("train", 0), ("validation", 1_000_000_000)):
        path = tmp_path / f"{split}.jsonl"
        header = {"dataset_version": 1, "encoding_version": 1, "spec": spec,
                  "split": split, "start": 0, "hands": 1}
        rows = [{"observation": obs, "label": 0, "seed": seed, "seq": i} for i in range(16)]
        path.write_text("\n".join(json.dumps(r) for r in [header, *rows]) + "\n")
        paths[split] = path
    checkpoint = tmp_path / "bc.pt"
    history = train_bc(paths["train"], paths["validation"], checkpoint, epochs=15)
    assert history[-1]["validation"]["all"]["loss"] < history[0]["validation"]["all"]["loss"]
    model, _ = load_checkpoint(checkpoint, spec)
    assert bc_metrics(model, paths["validation"], spec, "validation")["all"]["count"] == 16
    with pytest.raises(ValueError, match="split"):
        list(dataset_batches(paths["train"], spec, "validation"))


def test_generation_does_not_publish_a_partial_or_overwritten_file(tmp_path, monkeypatch):
    path = tmp_path / "data.jsonl"
    def fail(_self, _action):
        raise RuntimeError("simulation failed")
    monkeypatch.setattr(HandEpisode, "act", fail)
    with pytest.raises(RuntimeError, match="simulation failed"):
        generate(path, 1, split="train")
    assert not path.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_ppo_resume_preserves_rng_model_and_cumulative_provenance(tmp_path, monkeypatch):
    import random
    import rl.train as training

    torch.set_num_threads(1)
    obs = HandEpisode(2).current()
    obs["legal_actions"] = obs["legal_actions"][:2]
    torch.manual_seed(17)
    model = make_model(obs)
    spec = training_spec(Ruleset())
    initial = tmp_path / "initial.pt"
    optimizer = torch.optim.Adam(model.parameters())
    provenance = {"datasets": {"train": {"header": {"start": 7, "hands": 2}}}}
    save_checkpoint(initial, model, spec, stage="bc", optimizer=optimizer, progress=provenance)

    def rollout(model, **_kwargs):
        with torch.no_grad():
            logits, values = model(*batch([obs]))
            distribution = Categorical(logits=logits[0])
            label = distribution.sample()
            row = {"observation": obs, "label": int(label),
                   "old_log_prob": float(distribution.log_prob(label)),
                   "old_value": float(values[0]), "return": random.choice([-1.0, 1.0])}
        return [row], {"hands": 1, "engine_steps": 9, "decisions": 1, "choices": 1}

    monkeypatch.setattr(training, "collect_rollout", rollout)
    uninterrupted = tmp_path / "two.pt"
    first = tmp_path / "one.pt"
    resumed = tmp_path / "resumed.pt"
    train_ppo(initial, uninterrupted, updates=2, hands=1, seed=3)
    train_ppo(initial, first, updates=1, hands=1, seed=3)
    train_ppo(first, resumed, updates=1, hands=1, seed=3)
    expected_model, expected = load_checkpoint(uninterrupted, spec)
    actual_model, actual = load_checkpoint(resumed, spec)
    for name, value in actual_model.state_dict().items():
        torch.testing.assert_close(value, expected_model.state_dict()[name], rtol=0, atol=0)
    assert actual["progress"]["bc"] == provenance
    assert actual["progress"]["completed"] == 2
    assert actual["progress"]["cumulative"]["engine_steps"] == 18
    assert actual["progress"]["cumulative"]["choices"] == 2
    torch.testing.assert_close(actual["torch_rng"], expected["torch_rng"])
    assert actual["python_rng"] == expected["python_rng"]


def test_paired_evaluation_does_not_depend_on_candidate_order():
    from rl.evaluate import evaluate

    torch.set_num_threads(1)
    forward = evaluate(["random", "untrained", "greedy"], walls=1, opponent="auto")
    reverse = evaluate(["greedy", "untrained", "random"], walls=1, opponent="auto")
    assert forward["summary"] == reverse["summary"]
    assert "paired_vs_greedy" in forward["summary"]["untrained"]
    assert forward["summary"]["untrained"]["hands"] == 4
    assert len({r["seed"] for r in forward["hands"]["untrained"]}) == 1
    assert 1 <= forward["summary"]["greedy"]["mean_rank"] <= 4
    assert forward["summary"]["greedy"]["rank_unit"] == "hand"
    assert forward["summary"]["greedy"]["mean_match_net_payment"] is None


def test_random_policy_samples_optional_actions_and_ignores_global_rng():
    import random
    from rl.evaluate import _RandomStrategy

    obs = {"legal_actions": [{"type": "HU"}, {"type": "CHI"}, {"type": "PASS"}]}
    policy = _RandomStrategy(42)
    selected = [policy.choose(obs) for _ in range(30)]
    assert {action["type"] for action in selected} == {"HU", "CHI", "PASS"}
    assert all(action in obs["legal_actions"] for action in selected)
    random.seed(123)
    repeated = _RandomStrategy(42)
    assert [repeated.choose(obs) for _ in range(30)] == selected


def test_match_metrics_use_completed_totals_and_count_hand_rates(monkeypatch):
    import rl.evaluate as evaluation

    def match(seed, learner, policy, fixed, rules):
        other = (learner + 1) % 4
        first = [-30] * 4
        first[learner] = 90
        second = [-30] * 4
        second[other] = 90
        summaries = [
            {"payments": first, "winner": learner, "win_source": "TSUMO",
             "dealer_pid": 0, "hand_index": 1},
            {"payments": second, "winner": other, "win_source": "RON", "ron_from": learner,
             "dealer_pid": 1, "hand_index": 2},
        ]
        return summaries, [a + b for a, b in zip(first, second)]

    monkeypatch.setattr(evaluation, "_play_match", match)
    result = evaluation.evaluate(["greedy"], walls=1, unit="jang")
    metrics = result["summary"]["greedy"]
    assert metrics["hands"] == 8
    assert metrics["matches"] == 4
    assert metrics["mean_hand_net_payment"] == 30
    assert metrics["mean_match_net_payment"] == 60
    assert metrics["mean_rank"] == 1.5  # Two players tied at +60, not a pid tiebreak.
    assert metrics["rank_unit"] == "jang"
    assert metrics["win_rate"] == 0.5
    assert metrics["deal_in_rate"] == 0.5
    assert len(result["matches"]["greedy"]) == 4


def test_match_net_score_excludes_initial_points(monkeypatch):
    import rl.evaluate as evaluation
    from bots.greedy import GreedyBotStrategy

    def run(session):
        # Use the real SessionService initialization, including its starting balance.
        session.totals[0] += 300
        for pid in (1, 2, 3):
            session.totals[pid] -= 100
        return []

    monkeypatch.setattr(evaluation._BoundedMatch, "run", run)
    _, net = evaluation._play_match(2, 0, GreedyBotStrategy(), GreedyBotStrategy(), Ruleset())
    assert net == [300, -100, -100, -100]
    assert sum(net) == 0


def test_flower_ron_is_not_counted_as_a_discard_deal_in(monkeypatch):
    import rl.evaluate as evaluation

    def match(seed, learner, policy, fixed, rules):
        winner = (learner + 1) % 4
        payments = [0] * 4
        payments[learner], payments[winner] = -100, 100
        return [{"payments": payments, "winner": winner, "win_source": "RON",
                 "ron_from": learner, "dealer_pid": 0, "hand_index": 1,
                 "flower_win_type": "qi_qiang_yi"}], payments

    monkeypatch.setattr(evaluation, "_play_match", match)
    metrics = evaluation.evaluate(["greedy"], unit="jang", walls=1)["summary"]["greedy"]
    assert metrics["mean_match_net_payment"] == -100
    assert metrics["win_rate"] == 0
    assert metrics["deal_in_rate"] == 0
