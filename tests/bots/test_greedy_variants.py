"""Behavioral contracts for independent Greedy teacher ablations."""
from copy import deepcopy

import pytest

from bots.greedy import GreedyBotStrategy
from bots.greedy_variants import GreedyDefenseStrategy, GreedyLookaheadStrategy
from domain.rules.ruleset import Ruleset
from rl.env import HandEpisode


def reaction_fixture() -> dict:
    """A real seed-0 decision where retaining the pre-discard hand misses a claim."""
    return {
        "player": 0, "phase": "REACTION", "drawn": None,
        "hand": [16, 19, 32, 6, 17, 9, 27, 17, 10, 17, 1, 23, 20, 28, 32, 17],
        "melds": [], "melds_all": [[], [], [], []], "rivers": [[], [32], [], []],
        "last_discard": {"pid": 1, "tile": 32}, "blocked_discards": [],
        "legal_actions": [{"type": "PASS"}, {"type": "PONG"}],
    }


def test_lookahead_changes_claim_but_defense_keeps_original_reaction():
    obs = reaction_fixture()
    saved = deepcopy(obs)
    assert GreedyBotStrategy().choose(obs) == {"type": "PASS"}
    assert GreedyDefenseStrategy().choose(obs) == {"type": "PASS"}
    assert GreedyLookaheadStrategy().choose(obs) == {"type": "PONG"}
    assert obs == saved


def defense_fixture() -> dict:
    """West is useful to no opponent when all four copies are visible; North is not."""
    hand = [0, 2, 4, 6, 8, 9, 11, 13, 15, 17, 18, 20, 22, 24, 29, 29]
    return {
        "player": 0, "phase": "TURN", "hand": hand, "drawn": 30, "melds": [],
        "melds_all": [[], [], [], []], "rivers": [[], [29, 29], [], []],
        "players": [{"declared_ting": False, "melds": []},
                    {"declared_ting": True, "melds": []},
                    {"declared_ting": False, "melds": []},
                    {"declared_ting": False, "melds": []}],
        "legal_actions": [{"type": "DISCARD", "tile": 30, "from": "drawn"},
                          {"type": "DISCARD", "tile": 29, "from": "hand"}],
    }


def test_defense_uses_visible_threat_and_does_not_treat_river_as_furiten():
    obs = defense_fixture()
    saved = deepcopy(obs)
    assert GreedyBotStrategy().choose(obs)["tile"] == 30
    assert GreedyDefenseStrategy().choose(obs)["tile"] == 29
    assert obs == saved
    # One previously discarded honor is not guaranteed safe under Taiwan rules.
    obs["rivers"] = [[], [29], [30, 30, 30], []]
    assert GreedyDefenseStrategy().choose(obs)["tile"] == 30
    obs["players"][1]["declared_ting"] = False
    assert GreedyDefenseStrategy().choose(obs) == GreedyBotStrategy().choose(obs)


def test_defense_turn_ignores_hidden_fields_and_recognizes_four_exposed_melds():
    obs = defense_fixture()
    obs["wall"] = [30] * 60
    obs["players"][1]["hand"] = [30] * 16
    assert GreedyDefenseStrategy().choose(obs)["tile"] == 29
    obs["wall"] = [29] * 60
    obs["players"][1]["hand"] = [29] * 16
    assert GreedyDefenseStrategy().choose(obs)["tile"] == 29
    obs["players"][1]["declared_ting"] = False
    melds = [{"type": "PONG", "tiles": [t] * 3} for t in (1, 3, 5, 7)]
    obs["players"][1]["melds"] = melds
    obs["melds_all"][1] = melds
    assert GreedyDefenseStrategy().choose(obs)["tile"] == 29
    obs["players"][1]["melds"] = melds[:3]
    obs["melds_all"][1] = melds[:3]
    assert GreedyDefenseStrategy().choose(obs) == GreedyBotStrategy().choose(obs)


def test_defense_preserves_near_ready_attack_despite_a_lower_risk_discard():
    obs = defense_fixture()
    obs["hand"] = list(range(9)) + [9, 10, 11, 27, 27, 12, 13]
    obs["drawn"] = 28
    obs["rivers"] = [[], [27, 27], [], []]
    obs["legal_actions"] = [{"type": "DISCARD", "tile": 28, "from": "drawn"},
                            {"type": "DISCARD", "tile": 27, "from": "hand"}]
    assert GreedyBotStrategy().choose(obs)["tile"] == 28
    assert GreedyDefenseStrategy().choose(obs)["tile"] == 28


@pytest.mark.parametrize("strategy", [GreedyDefenseStrategy, GreedyLookaheadStrategy])
def test_variants_prioritize_hu_and_ignore_unavailable_hidden_fields(strategy):
    obs = reaction_fixture()
    before = strategy().choose(obs)
    obs["wall"] = [1] * 90
    obs["opponent_hands"] = [[2] * 16] * 3
    assert strategy().choose(obs) == before
    hu = {"type": "HU", "source": "RON"}
    obs["legal_actions"].append(hu)
    assert strategy().choose(obs) == hu
    obs["last_discard"] = None
    obs["legal_actions"] = [{"type": "PASS"}]
    assert strategy().choose(obs) == {"type": "PASS"}


@pytest.mark.parametrize("same_tile", [False, True])
def test_lookahead_respects_engine_post_chi_discards(same_tile):
    rules = Ruleset(allow_same_tile_discard_after_chi=same_tile)
    episode = HandEpisode(0, rules)
    env = episode.env
    env.players[0].hand = [0, 1, 2, 3, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26]
    env.players[0].drawn = None
    upstream = next(pid for pid, index in env._seat_index.items()
                    if index == (env._seat_index[0] - 1) % 4)
    env.players[upstream].river = [2]
    env.last_discard = {"pid": upstream, "tile": 2}
    env.phase = "REACTION"
    env.reaction_queue = [0]
    env.reaction_idx = 0
    obs = episode.current()
    chi = next(a for a in obs["legal_actions"] if a.get("use") == [0, 1])
    # The engine is the independent oracle for the claimed-tile discard restriction.
    episode.act(chi)
    post = episode.current()
    discards = [a["tile"] for a in post["legal_actions"] if a["type"] == "DISCARD"]
    assert (2 in discards) == same_tile
    assert GreedyLookaheadStrategy(rules).choose(obs) in obs["legal_actions"]


def test_chi_lock_changes_lookahead_choice_when_only_forbidden_discard_would_help():
    obs = reaction_fixture()
    obs.update(hand=[6, 1, 28, 22, 2, 4, 4, 10, 20, 7, 16, 2, 0, 0, 1, 2],
               rivers=[[], [], [], [2]], last_discard={"pid": 3, "tile": 2},
               legal_actions=[{"type": "PASS"}, {"type": "CHI", "use": [0, 1]}])
    assert GreedyLookaheadStrategy().choose(obs) == {"type": "PASS"}
    allowed = GreedyLookaheadStrategy(Ruleset(allow_same_tile_discard_after_chi=True))
    assert allowed.choose(obs) == {"type": "CHI", "use": [0, 1]}


@pytest.mark.parametrize("strategy", [GreedyDefenseStrategy, GreedyLookaheadStrategy])
def test_real_hand_remains_legal_deterministic_and_visible(strategy):
    episode = HandEpisode(11)
    bot = strategy()
    while (obs := episode.current()) is not None:
        saved = deepcopy(obs)
        chosen = bot.choose(obs)
        assert chosen in obs["legal_actions"]
        assert bot.choose(obs) == chosen
        assert obs == saved
        if strategy is GreedyLookaheadStrategy and obs["phase"] == "TURN":
            assert chosen == GreedyBotStrategy().choose(obs)
        episode.act(chosen)
    assert sum(episode.payments()) == 0
