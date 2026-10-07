"""Round-trip contracts for private records, including simultaneous claim decisions."""
from copy import deepcopy
import json

import pytest

from bots.greedy import GreedyBotStrategy
from domain.gameplay.game_env import Mahjong16Env
from domain.gameplay.recording import HandRecorder, private_state, replay_hand
from domain.rules.ruleset import Ruleset
from tests.helpers.tile_pool import TilePool


def _deal_wall(monkeypatch, hands, drawn, *, flowers=False):
    """Arrange a real full wall instead of mutating the recorded engine after reset."""
    pool = TilePool(include_flowers=flowers)
    for hand in hands:
        pool.take(hand)
    pool.take([drawn])
    draws = [hands[pid][index] for index in range(16) for pid in range(4)] + [drawn]
    wall = pool.remaining() + list(reversed(draws))
    monkeypatch.setattr("domain.table.deal.full_wall", lambda *_: list(wall))


@pytest.mark.parametrize("allow_hu", [True, False])
def test_recording_preserves_gameplay_and_replays_every_step(allow_hu):
    rules = Ruleset(allow_hu=allow_hu)
    recorder = HandRecorder()
    env = Mahjong16Env(rules, seed=7, recorder=recorder)
    baseline = Mahjong16Env(rules, seed=7)
    env.reset()
    baseline.reset()
    bot = GreedyBotStrategy()
    while not env.done:
        pid = env.turn if env.phase == "TURN" else env.pending_reactions()[-1]
        action = bot.choose(env._obs(pid))
        assert env.step(action, pid=pid) == baseline.step(action, pid=pid)
        assert private_state(env) == private_state(baseline)
    # Serialization is part of the contract, not just in-memory equality.
    document = json.loads(json.dumps(recorder.document()))
    replay = replay_hand(document)
    assert private_state(replay) == private_state(baseline)
    assert document["status"] == "completed"
    assert sum(document["settlement"]["payments"]) == 0
    if not allow_hu:
        assert document["settlement"]["winner"] is None
        assert document["settlement"]["payments"] == [0, 0, 0, 0]


@pytest.mark.parametrize("submit_chi", [True, False])
def test_reaction_record_distinguishes_overridden_choice_from_no_reply(monkeypatch, submit_chi):
    hands = [
        [4, 0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 18, 19, 20, 21],
        [2, 3, 9, 10, 11, 12, 13, 14, 15, 16, 22, 23, 24, 25, 27, 28],
        [4, 4, 5, 6, 16, 17, 18, 19, 20, 21, 22, 23, 30, 29, 31, 32],
        [0, 1, 7, 8, 12, 13, 14, 15, 24, 25, 26, 27, 28, 30, 29, 33],
    ]
    _deal_wall(monkeypatch, hands, drawn=8)
    recorder = HandRecorder()
    env = Mahjong16Env(Ruleset(include_flowers=False,
                              randomize_seating_and_dealer=False), recorder=recorder)
    env.reset()
    env.step({"type": "DISCARD", "tile": 4, "from": "hand"}, pid=0)
    if submit_chi:
        env.step({"type": "CHI", "use": [2, 3]}, pid=1)
    env.step({"type": "PONG"}, pid=2)
    document = recorder.document()
    assert env.turn == 2
    assert env.players[2].melds == [{"type": "PONG", "tiles": [4, 4, 4], "from_pid": 0}]
    assert document["steps"][-1]["info"]["resolved_claim"]["type"] == "PONG"
    assert document["steps"][-1]["unanswered"] == ([3] if submit_chi else [1, 3])
    assert [step["action"]["type"] for step in document["steps"]] == (
        ["DISCARD", "CHI", "PONG"] if submit_chi else ["DISCARD", "PONG"])
    assert private_state(replay_hand(document)) == private_state(env)
    assert document["status"] == "incomplete"
    assert document["settlement"] is None


def test_opening_flower_win_records_completion_without_actions(monkeypatch):
    pool = TilePool(include_flowers=True)
    flowers = pool.take(range(34, 42))
    wall = pool.remaining() + list(reversed(flowers))
    monkeypatch.setattr("domain.table.deal.full_wall", lambda *_: list(wall))
    recorder = HandRecorder()
    env = Mahjong16Env(Ruleset(randomize_seating_and_dealer=False), recorder=recorder)
    env.reset()
    document = recorder.document()
    assert document["steps"] == []
    assert document["settlement"]["winner"] == 0
    assert document["settlement"]["flower_win_type"] == "ba_xian"
    assert document["settlement"]["payments"][0] > 0
    assert private_state(replay_hand(document)) == private_state(env)


@pytest.mark.parametrize("kind", ["HU", "TING", "ANGANG", "DISCARD"])
@pytest.mark.parametrize("omit_optional", [True, False])
def test_dealer_action_replays_with_engine_defaults(monkeypatch, kind, omit_optional):
    hand = [0] * 3 + [1] * 3 + [2] * 3 + [3] * 3 + [4] * 3 + [8]
    drawn = 0 if kind == "ANGANG" else 8
    pool = TilePool()
    pool.take(hand + [drawn])
    remaining = pool.remaining()
    hands = [hand] + [remaining[index:index + 16] for index in (0, 16, 32)]
    _deal_wall(monkeypatch, hands, drawn)
    recorder = HandRecorder()
    env = Mahjong16Env(Ruleset(include_flowers=False,
                              randomize_seating_and_dealer=False), recorder=recorder)
    baseline = Mahjong16Env(env.rules)
    env.reset()
    baseline.reset()
    action = next(action for action in env.legal_actions()
                  if action["type"] == kind
                  and (kind != "DISCARD" or action.get("from") == "hand"))
    if omit_optional:
        action = dict(action)
        action.pop("source", None)
        action.pop("waits", None)
        if action.get("from") == "hand":
            action.pop("from")
    assert env.step(action) == baseline.step(action)
    assert private_state(env) == private_state(baseline)
    assert recorder.document()["steps"][0]["action"] == action
    assert private_state(replay_hand(recorder.document())) == private_state(env)
    if kind == "HU":
        assert recorder.document()["settlement"]["winner"] == 0
        assert recorder.document()["settlement"]["payments"][0] > 0
    elif kind == "TING":
        assert env.players[0].declared_ting
    elif kind == "ANGANG":
        assert env.players[0].melds[0]["type"] == "ANGANG"
        assert env.players[0].drawn is not None


def test_multiple_resets_preserve_old_records_and_exact_presets():
    recorder = HandRecorder()
    env = Mahjong16Env(Ruleset(), seed=8, recorder=recorder)
    env.reset()
    first = recorder.document()
    env.preset_seat_winds = ["W", "N", "E", "S"]
    env.preset_dealer_pid = 2
    env.preset_quan_feng = "S"
    env.preset_dealer_streak = 3
    env.reset()
    second = recorder.document()
    assert first["hand_id"] != second["hand_id"]
    assert first["setup"]["wall"] != second["setup"]["wall"]
    assert recorder.records[0] == first
    replay = replay_hand(second)
    assert replay.turn == 2
    assert replay.dealer_streak == 3
    assert replay.quan_feng == "S"
    assert private_state(replay) == private_state(env)


@pytest.mark.parametrize(
    "field", ["engine_version", "format_version", "wall", "step", "settlement"],
)
def test_replay_rejects_changed_records(field):
    recorder = HandRecorder()
    env = Mahjong16Env(Ruleset(), seed=7, recorder=recorder)
    env.reset()
    env.step(next(a for a in env.legal_actions() if a["type"] == "DISCARD"))
    document = deepcopy(recorder.document())
    if field in ("engine_version", "format_version"):
        document[field] = "wrong"
    elif field == "wall":
        document["setup"]["wall"][0] = -1
    elif field == "step":
        document["steps"][0]["seq"] = 99
    else:
        document["settlement"] = {"payments": [1, 0, 0, 0]}
    with pytest.raises(ValueError):
        replay_hand(document)


def test_illegal_action_and_external_mutation_do_not_create_recorded_steps():
    recorder = HandRecorder()
    env = Mahjong16Env(Ruleset(), seed=7, recorder=recorder)
    env.reset()
    with pytest.raises(ValueError, match="非法"):
        env.step({"type": "PASS"})
    assert recorder.document()["steps"] == []
    action = next(a for a in env.legal_actions() if a["type"] == "DISCARD")
    env.discard_count += 1
    with pytest.raises(ValueError, match="之外"):
        env.step(action)
    assert recorder.document()["steps"] == []
