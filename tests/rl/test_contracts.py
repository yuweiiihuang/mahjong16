"""RL contracts not covered by the engine's existing rule and scoring tests."""
from copy import deepcopy

import pytest

from bots.greedy import GreedyBotStrategy
from bots.policies import AutoStrategy
from domain.gameplay.recording import HandRecorder
from domain.rules.ruleset import Ruleset
from rl.encoding import encode
from rl.env import HandEpisode, LearnerEpisode
from rl.selfplay import hand_seed


def test_player_view_hides_other_hands_wall_and_concealed_kong_identity():
    episode = HandEpisode(3)
    env = episode.env
    pid = episode.current()["player"]
    other = (pid + 1) % 4
    env.players[other].melds = [{"type": "ANGANG", "tiles": [0] * 4}]
    before = episode.current()
    env.players[other].melds[0]["tiles"] = [9] * 4
    env.players[other].hand = [18] * len(env.players[other].hand)
    env.wall.reverse()
    env._public_live = [0] * 34
    after = episode.current()
    assert after == before
    assert encode(after) == encode(before)
    assert after["players"][other]["melds"][0]["tiles"] == [None] * 4
    assert "live_public" not in after
    assert GreedyBotStrategy().choose(before) == GreedyBotStrategy().choose(after)


def test_encoding_uses_actual_seat_order_and_keeps_action_source():
    obs = HandEpisode(4).current()
    moved = deepcopy(obs)
    permutation = [2, 0, 3, 1]  # old pid -> new pid; not a cyclic shift
    for field in ("players", "rivers", "seat_winds", "melds_all"):
        moved[field] = [obs[field][permutation.index(i)] for i in range(4)]
    moved["player"] = permutation[obs["player"]]
    moved["dealer"] = permutation[obs["dealer"]]
    if moved["last_discard"]:
        moved["last_discard"]["pid"] = permutation[obs["last_discard"]["pid"]]
    assert encode(moved) == encode(obs)
    obs["legal_actions"] = [
        {"type": "DISCARD", "tile": 3, "from": "hand"},
        {"type": "DISCARD", "tile": 3, "from": "drawn"},
        {"type": "CHI", "use": [1, 2]}, {"type": "CHI", "use": [2, 4]},
    ]
    _, candidates = encode(obs)
    assert candidates[0] != candidates[1]
    assert candidates[2] != candidates[3]


def test_invalid_action_and_step_limit_do_not_change_hand():
    episode = HandEpisode(0, max_steps=1)
    obs = episode.current()
    with pytest.raises(ValueError, match="legal"):
        episode.act({"type": "DISCARD", "tile": 99})
    assert episode.current() == obs
    episode.act(AutoStrategy().choose(obs))
    after = episode.current()
    with pytest.raises(RuntimeError, match="step limit"):
        episode.act(AutoStrategy().choose(after))
    assert episode.current() == after


def test_learner_transitions_remain_same_player_through_reactions_and_dead_wall():
    rules = Ruleset(include_flowers=False, allow_hu=False, allow_zimo=False)
    episode = LearnerEpisode(8, 2, rules, opponent=AutoStrategy())
    episode.env.wall = episode.env.wall[:20]
    seen = []
    while (obs := episode.current()) is not None:
        assert obs["player"] == 2
        nxt, reward, done = episode.step(AutoStrategy().choose(obs))
        seen.append(obs["phase"])
        assert done == (nxt is None)
        assert reward == 0
        if nxt:
            assert nxt["player"] == 2
    assert seen
    assert episode.payments() == [0, 0, 0, 0]
    with pytest.raises(ValueError, match="complete"):
        episode.step({"type": "PASS"})


def test_terminal_reward_matches_recorded_settlement_and_is_not_engine_zero():
    rules = Ruleset(include_flowers=False, enable_wind_flower_scoring=False)
    episode = LearnerEpisode(0, 0, rules, opponent=AutoStrategy())
    env = episode.env
    env.turn, env.phase = 0, "TURN"
    env.players[0].hand = [t for t in range(5) for _ in range(3)] + [8]
    env.players[0].drawn = 8
    env.players[0].melds = []
    env.players[0].declared_ting = False
    env.recorder = HandRecorder()
    env.recorder.begin(env)
    env.recorder.initialized(env)
    hu = next(a for a in episode.current()["legal_actions"] if a["type"] == "HU")
    nxt, reward, done = episode.step(hu)
    recorded = env.recorder.document()
    assert done and nxt is None
    assert recorded["steps"][-1]["rewards"] == [0, 0, 0, 0]
    assert reward == recorded["settlement"]["payments"][0] / 100
    assert reward > 0


def test_split_and_training_streams_do_not_overlap():
    assert hand_seed("train", 0) == 0
    assert hand_seed("train", 500_000_000) == 500_000_000
    assert hand_seed("validation", 0) == 1_000_000_000
    assert hand_seed("test", 0) == 2_000_000_000
    with pytest.raises(ValueError):
        hand_seed("train", 1_000_000_000)
