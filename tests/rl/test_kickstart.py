"""Duplicate-action merging, sampling temperature and online-teacher imitation for PPO."""
from copy import deepcopy
import math

import pytest

torch = pytest.importorskip("torch")

from domain.rules.ruleset import Ruleset
from rl.env import HandEpisode
from rl.net import PolicyValueNet
from rl.train import collect_rollout, policy_logits, representatives, update_ppo


def _duplicate_discard_obs() -> dict:
    obs = HandEpisode(2).current()
    tile = obs["legal_actions"][0]["tile"]
    obs["legal_actions"] = [{"type": "DISCARD", "tile": tile, "from": "hand"},
                            {"type": "DISCARD", "tile": tile, "from": "drawn"},
                            {"type": "DISCARD", "tile": (tile + 1) % 34, "from": "hand"}]
    return obs


def test_merging_duplicate_discards_keeps_each_distinct_actions_probability():
    obs = _duplicate_discard_obs()
    assert representatives(obs["legal_actions"]) == [0, 0, 2]
    logits = torch.tensor([[math.log(.3), math.log(.2), math.log(.5)]])
    merged = policy_logits(logits, [obs], merge_duplicates=True).softmax(-1)
    torch.testing.assert_close(merged, torch.tensor([[.5, 0., .5]]))
    sharp = policy_logits(logits, [obs], merge_duplicates=True, temperature=.5).softmax(-1)
    torch.testing.assert_close(sharp, torch.tensor([[.5, 0., .5]]))  # equal mass stays equal
    with pytest.raises(ValueError, match="Temperature"):
        policy_logits(logits, [obs], temperature=0)


class _LastActionTeacher:
    """Always picks the last legal action, so labels are independent of the student."""

    def choose(self, obs: dict) -> dict:
        return obs["legal_actions"][-1]


def test_rollout_and_update_share_temperature_and_teacher_labels_use_representatives():
    torch.set_num_threads(1)
    torch.manual_seed(0)
    model = PolicyValueNet(1035, 82, hidden=16)
    rows, metrics = collect_rollout(model, seed=1, start=0, hands=1, rules=Ruleset(),
                                    temperature=.5, merge_duplicates=True,
                                    teacher=_LastActionTeacher())
    assert metrics["teacher_labels"] > 0
    for r in rows:
        legal = r["observation"]["legal_actions"]
        if r["teacher_label"] is not None:
            assert r["teacher_label"] == representatives(legal)[-1]
            assert not any(a["type"] == "HU" for a in legal)
    frozen = torch.optim.SGD(model.parameters(), lr=0)
    same = update_ppo(deepcopy(model), frozen, rows, epochs=1, temperature=.5,
                      merge_duplicates=True)
    assert same["kl"] == pytest.approx(0, abs=1e-6) and not same["early_stopped"]
    mismatched = update_ppo(deepcopy(model), frozen, rows, epochs=1, temperature=1.,
                            merge_duplicates=True)
    assert mismatched["kl"] > 1e-4

    student = deepcopy(model)
    taught = [r for r in rows if r["teacher_label"] is not None]
    inputs = student.prepare([r["observation"] for r in taught])
    targets = torch.tensor([r["teacher_label"] for r in taught])

    def teacher_log_prob() -> float:
        with torch.no_grad():
            logits = policy_logits(student(*inputs)[0], [r["observation"] for r in taught],
                                   temperature=.5, merge_duplicates=True)
            return float(logits.log_softmax(-1).gather(1, targets[:, None]).mean())

    before = teacher_log_prob()
    imitation = update_ppo(student, torch.optim.SGD(student.parameters(), lr=.05), rows,
                           epochs=1, temperature=.5, merge_duplicates=True,
                           teacher_coef=1., surrogate=False)
    assert imitation["optimizer_steps"] >= 1 and teacher_log_prob() > before
