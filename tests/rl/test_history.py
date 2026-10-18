"""Own-decision causality, chronological datasets, and per-hand inference resets."""
import json

import pytest

torch = pytest.importorskip("torch")

from domain.rules.ruleset import Ruleset
from rl.encoding import encode
from rl.env import HandEpisode, training_spec
from rl.evaluate import _VisibleStrategy
from rl.history import DecisionHistory
from rl.net import PolicyValueNet
from rl.train import collect_rollout, dataset_batches


def test_memory_snapshots_are_causal_bounded_and_player_specific():
    obs = HandEpisode(2).current()
    history = DecisionHistory()
    first = history.observe(obs)
    assert first["decision_history"] == []
    expected = []
    for tile in range(5):
        visible = {**obs, "drawn": tile}
        action = visible["legal_actions"][0]
        state, actions = encode(visible)
        expected.append((state, actions[0]))
        history.append(visible, action)
    assert first["decision_history"] == []
    assert history.observe(obs)["decision_history"] == expected[-3:]
    with pytest.raises(ValueError, match="different player"):
        history.observe({**obs, "player": (obs["player"] + 1) % 4})


def test_sequence_reader_keeps_forced_moves_and_resets_hands_across_batches(tmp_path):
    obs = HandEpisode(2).current()
    pid = obs["player"]
    other = {**obs, "player": (pid + 1) % 4}
    forced = {**obs, "drawn": 9, "legal_actions": obs["legal_actions"][:1]}
    rows = [{"seed": 0, "seq": 0, "observation": forced, "label": 0},
            {"seed": 0, "seq": 1, "observation": other, "label": 0},
            {"seed": 0, "seq": 2, "observation": obs, "label": 0},
            {"seed": 1, "seq": 0, "observation": obs, "label": 0}]
    spec = training_spec(Ruleset())
    header = {"dataset_version": 1, "encoding_version": 1, "spec": spec,
              "split": "train", "start": 0, "hands": 2}
    path = tmp_path / "data.jsonl"

    def write():
        path.write_text("\n".join(json.dumps(r) for r in [header, *rows]) + "\n")

    write()
    data = [row for group in dataset_batches(path, spec, "train", size=1, history=True)
            for row in group]
    assert len(data) == 3  # The forced move is context, not a BC classification target.
    assert data[0]["observation"]["decision_history"] == []  # Other player.
    state, actions = encode(forced)
    assert data[1]["observation"]["decision_history"] == [(state, actions[0])]
    assert data[2]["observation"]["decision_history"] == []  # New hand.
    rows[2]["seq"] = 3
    write()
    with pytest.raises(ValueError, match="consecutive"):
        list(dataset_batches(path, spec, "train", history=True))


def test_temporal_policy_uses_order_masks_padding_and_backpropagates():
    torch.set_num_threads(1)
    torch.manual_seed(4)
    obs = HandEpisode(2).current()
    past = DecisionHistory()
    past.append({**obs, "drawn": 1}, obs["legal_actions"][0])
    past.append({**obs, "drawn": 9}, obs["legal_actions"][1])
    a = past.observe(obs)
    b = {**a, "decision_history": list(reversed(a["decision_history"]))}
    model = PolicyValueNet(1035, 82, hidden=16, architecture="temporal")
    logits, values = model(*model.prepare([a, b, obs]))
    assert not torch.allclose(logits[0], logits[1], atol=1e-6, rtol=1e-6)
    packed = list(model.prepare([obs]))
    with torch.no_grad():
        expected = model(*packed)
        packed[3].fill_(11)  # All past slots are padding for an empty history.
        packed[4].fill_(13)
        actual = model(*packed)
    for x, y in zip(expected, actual):
        torch.testing.assert_close(x, y)
    (-logits.log_softmax(-1)[:, 0].mean() + values.square().mean()).backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())
    assert model.past_action.weight.grad.abs().sum() > 0


def test_match_strategy_resets_memory_when_engine_starts_a_new_hand():
    episode = HandEpisode(2)

    class Capture:
        architecture = "temporal"

        def __init__(self):
            self.lengths = []

        def choose(self, obs):
            self.lengths.append(len(obs["decision_history"]))
            return obs["legal_actions"][0]

    policy = Capture()
    strategy = _VisibleStrategy(episode.env, policy)
    obs = episode.current()
    strategy.choose(obs)
    strategy.choose(obs)
    episode.env.reset()
    strategy.choose(episode.current())
    assert policy.lengths == [0, 1, 0]


def test_ppo_rollout_snapshots_match_next_decision_and_reset_between_hands():
    torch.set_num_threads(1)
    torch.manual_seed(2)
    model = PolicyValueNet(1035, 82, hidden=16, architecture="temporal")
    rows, metrics = collect_rollout(model, seed=2, start=0, hands=2, rules=Ruleset())
    assert metrics["hands"] == 2
    hand = []
    completed = 0
    for row in rows:
        obs = row["observation"]
        assert len(obs["decision_history"]) == min(len(hand), 3)
        if hand:
            assert hand[-1]["next_observation"] == obs
        hand.append(row)
        if row["terminated"]:
            assert row["next_observation"] is None
            completed += 1
            hand = []
    assert completed == 2
