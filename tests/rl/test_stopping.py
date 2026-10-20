"""Selection is independent of validation-patience and action-sampling noise."""
from dataclasses import asdict
import math

import pytest

torch = pytest.importorskip('torch')

from rl.stopping import Patience
from rl.ppo_stopped import rollout_exact_kl


def test_patience_tiny_improvements_select_best_without_reset():
    p = Patience(3, .001, 1., 1.)
    for index, value in enumerate([.9998, .9997, .9996], 1):
        p.observe(value, index)
    assert p.stopped and p.best_index == 3 and p.anchor == 1.
    restored = Patience(**asdict(p))
    assert restored == p
    with pytest.raises(ValueError):
        restored.observe(.9, 3)
    with pytest.raises(ValueError):
        restored.observe(float('nan'), 4)
    # Negated scores permit small best-score changes without resetting meaningful patience.
    score = Patience(2, 20., 0., 0.)
    score.observe(-10., 4)
    score.observe(-15., 8)
    assert score.stopped and score.best_index == 8


def test_exact_kl_uses_all_actions_and_excludes_forced_rows():
    class Fixed:
        def prepare(self, observations):
            return (torch.tensor([len(o['legal_actions']) for o in observations]),)

        def __call__(self, lengths):
            logits = torch.full((len(lengths), 3), -torch.inf)
            for i, length in enumerate(lengths):
                logits[i, :length] = 0.
            return logits, torch.zeros(len(lengths))

    rows = [{'observation': {'legal_actions': [{}, {}]},
             'old_log_probs': [math.log(.25), math.log(.75)]},
            {'observation': {'legal_actions': [{}]}, 'old_log_probs': [0.]}]
    actual = rollout_exact_kl(Fixed(), rows)
    expected = .25 * math.log(.25 / .5) + .75 * math.log(.75 / .5)
    assert actual == pytest.approx(expected, abs=1e-7)
    rows[0]['old_log_probs'] = [0., 0.]
    with pytest.raises(ValueError, match='frozen rollout'):
        rollout_exact_kl(Fixed(), rows)
