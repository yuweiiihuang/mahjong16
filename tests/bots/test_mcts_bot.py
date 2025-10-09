"""Regression tests for the Monte Carlo Tree Search bot."""

from __future__ import annotations

import copy

from collections import Counter
from typing import Iterable, List, Tuple

import pytest

from bots import MCTSBot, MCTSBotConfig
from bots.mcts import MCTSNode, _encode_action_key
from core import Mahjong16Env, Ruleset
from core.tiles import Tile


def _build_rules() -> Ruleset:
    return Ruleset(
        include_flowers=False,
        dead_wall_mode="fixed",
        dead_wall_base=16,
        scoring_profile="taiwan_base",
        see_flower_see_wind=False,
        randomize_seating_and_dealer=False,
        enable_wind_flower_scoring=False,
        scoring_overrides_path=None,
    )


def _action_types(actions: Iterable[dict]) -> set[str]:
    return {(action.get("type") or "").upper() for action in actions}


def _action_id(bot: MCTSBot, action: dict) -> int:
    return _encode_action_key(action, bot._action_table, bot._action_lookup)


def test_mcts_bot_returns_legal_actions_during_turn():
    env = Mahjong16Env(_build_rules(), seed=7)
    bot = MCTSBot(env, MCTSBotConfig(simulations=6, rollout_depth=2, seed=0))

    obs = env.reset()
    for _ in range(12):
        actions = obs.get("legal_actions", [])
        assert actions, "environment must always provide legal actions"
        action = bot.choose(obs)
        assert action in actions
        obs, _reward, done, _info = env.step(action)
        if done:
            break


def test_mcts_bot_handles_reaction_candidates():
    env = Mahjong16Env(_build_rules(), seed=11)
    env.reset()

    env.phase = "REACTION"
    env.reaction_queue = [1, 2, 3]
    env.reaction_idx = 0
    env.last_discard = {"pid": 0, "tile": int(Tile.D6)}
    env.claims = []
    env.qiang_gang_mode = False
    env.done = False

    player = env.players[1]
    player.hand = [
        int(Tile.W1),
        int(Tile.W2),
        int(Tile.W3),
        int(Tile.W4),
        int(Tile.W5),
        int(Tile.W6),
        int(Tile.D4),
        int(Tile.D5),
        int(Tile.D6),
        int(Tile.D6),
        int(Tile.D6),
        int(Tile.D7),
        int(Tile.D8),
        int(Tile.D9),
        int(Tile.E),
        int(Tile.E),
    ]
    player.drawn = None
    player.melds = []
    player.declared_ting = False

    obs = env._obs(1)
    legal = obs.get("legal_actions", [])
    types = _action_types(legal)
    assert {"PASS", "CHI", "PONG", "HU"}.issubset(types)

    bot = MCTSBot(env, MCTSBotConfig(simulations=8, rollout_depth=2, seed=0))
    action = bot.choose(obs)
    assert action in legal


def test_mcts_rollout_heuristic_is_deterministic():
    rules = _build_rules()
    config = MCTSBotConfig(simulations=8, rollout_depth=2, seed=321)

    env = Mahjong16Env(rules, seed=5)
    obs = env.reset()
    bot = MCTSBot(env, config)

    value = bot._evaluate(env, obs["player"])
    assert value != 0.0

    first_action = bot.choose(obs)

    env_clone = Mahjong16Env(rules, seed=5)
    obs_clone = env_clone.reset()
    bot_clone = MCTSBot(env_clone, config)
    second_action = bot_clone.choose(obs_clone)

    assert second_action == first_action


def test_policy_prior_biases_winning_actions():
    env = Mahjong16Env(_build_rules(), seed=17)
    bot = MCTSBot(env, MCTSBotConfig(simulations=4, rollout_depth=1, seed=4))

    actions = [
        {"type": "PASS"},
        {"type": "PONG"},
        {"type": "HU"},
    ]

    priors = bot.policy_prior("REACTION", actions)
    assert pytest.approx(sum(priors), rel=1e-9) == 1.0

    pass_prior, pong_prior, hu_prior = priors
    assert hu_prior > pong_prior > pass_prior


def test_tree_reuse_accumulates_visits_between_calls():
    env = Mahjong16Env(_build_rules(), seed=23)
    config = MCTSBotConfig(simulations=6, rollout_depth=2, seed=5, reuse_tree=True)
    bot = MCTSBot(env, config)

    obs = env.reset()
    bot.choose(obs)

    root = bot._root_cache
    assert root is not None
    action_id = bot._last_action_id
    assert action_id is not None
    reused_child = root.children.get(action_id)
    assert reused_child is not None
    previous_visits = reused_child.visits

    bot.choose(obs)

    assert bot._root_cache is reused_child
    assert reused_child.visits > previous_visits


def test_progressive_widening_limit_scales_with_visits():
    env = Mahjong16Env(_build_rules(), seed=31)
    bot = MCTSBot(env, MCTSBotConfig(simulations=1, seed=0))

    obs = env.reset()
    root, _snapshot = bot._prepare_root(obs, obs["legal_actions"])

    limits: List[int] = []
    for visits in (0, 1, 4, 16):
        root.visits = visits
        limits.append(bot._progressive_widening_limit(root))

    assert limits[0] >= 1
    assert limits == sorted(limits)
    assert limits[-1] > limits[1]


class _DummyRolloutEnv:
    def __init__(self) -> None:
        self.depth = 0
        self.done = False
        self._action = {"type": "DISCARD", "tile": 0, "from": "drawn"}

    def legal_actions(self) -> List[dict]:
        return [copy.deepcopy(self._action)]

    def step(self, action: dict) -> Tuple[dict, float, bool, dict]:
        self.depth += 1
        obs = {
            "phase": "TURN",
            "hand": [],
            "melds": [],
            "drawn": None,
            "legal_actions": [copy.deepcopy(self._action)],
        }
        return obs, 0.0, False, {}


class _DepthTrackingMCTSBot(MCTSBot):
    def _evaluate(self, env: _DummyRolloutEnv, root_player: int) -> float:  # type: ignore[override]
        return float(env.depth)


def test_rollout_depth_hits_configured_cap():
    env = _DummyRolloutEnv()
    bot = _DepthTrackingMCTSBot(env, MCTSBotConfig(simulations=1, seed=9))

    template_obs = {
        "phase": "TURN",
        "hand": [],
        "melds": [],
        "drawn": None,
        "legal_actions": env.legal_actions(),
    }

    depths = []
    for _ in range(5):
        env.depth = 0
        obs = copy.deepcopy(template_obs)
        value = bot._rollout(env, obs, False, 0)
        depths.append(int(value))

    assert all(depth == bot.config.rollout_depth for depth in depths)


def test_rave_updates_prior_actions_in_path():
    env = Mahjong16Env(_build_rules(), seed=41)
    bot = MCTSBot(env, MCTSBotConfig(simulations=1, seed=0))

    pass_action = {"type": "PASS"}
    discard_action = {"type": "DISCARD", "tile": 1, "from": "drawn"}
    call_action = {"type": "DISCARD", "tile": 2, "from": "drawn"}

    root = MCTSNode(
        player=0,
        phase="TURN",
        unexpanded_actions=[(_action_id(bot, pass_action), 1.0)],
    )
    discard_id = _action_id(bot, discard_action)
    child_one = MCTSNode(
        player=1,
        phase="TURN",
        unexpanded_actions=[(discard_id, 1.0)],
        parent=root,
        action_id=discard_id,
    )
    call_id = _action_id(bot, call_action)
    child_two = MCTSNode(
        player=0,
        phase="TURN",
        unexpanded_actions=[(call_id, 1.0)],
        parent=child_one,
        action_id=call_id,
    )

    path = [root, child_one, child_two]
    bot._backpropagate(path, 0.5)

    follow_up = root.rave_stats.get(child_one.action_id)
    assert follow_up is not None
    total, visits = follow_up
    assert visits == 1
    assert total == pytest.approx(0.5)
    follow_up_child = child_one.rave_stats.get(child_two.action_id)
    assert follow_up_child is not None
    total_child, visits_child = follow_up_child
    assert visits_child == 1
    assert total_child == pytest.approx(0.5)


def test_rave_selection_prefers_amaf_superior_child():
    env = Mahjong16Env(_build_rules(), seed=43)
    config = MCTSBotConfig(simulations=1, seed=0, puct_c=0.0)
    bot = MCTSBot(env, config)

    action_a = {"type": "DISCARD", "tile": 3, "from": "drawn"}
    action_b = {"type": "DISCARD", "tile": 4, "from": "drawn"}
    key_a = _action_id(bot, action_a)
    key_b = _action_id(bot, action_b)
    root = MCTSNode(
        player=0,
        phase="TURN",
        unexpanded_actions=[(key_a, 0.5), (key_b, 0.5)],
    )

    child_a = MCTSNode(
        player=1,
        phase="TURN",
        unexpanded_actions=[(key_a, 1.0)],
        parent=root,
        action_id=key_a,
        prior=0.5,
    )
    child_b = MCTSNode(
        player=1,
        phase="TURN",
        unexpanded_actions=[(key_b, 1.0)],
        parent=root,
        action_id=key_b,
        prior=0.5,
    )

    child_a.visits = 5
    child_a.w = 0.0
    child_a.q = 0.0
    child_b.visits = 5
    child_b.w = 0.0
    child_b.q = 0.0

    root.children = {key_a: child_a, key_b: child_b}
    root.visits = 10
    root.rave_stats[key_a] = (-2.0, 2)
    root.rave_stats[key_b] = (4.0, 2)

    chosen = bot._select_child(root)
    assert chosen is child_b


def test_ismcts_determinization_preserves_hidden_tile_pool():
    env = Mahjong16Env(_build_rules(), seed=47)
    obs = env.reset()
    bot = MCTSBot(env, MCTSBotConfig(simulations=1, seed=3))

    snapshot = env.snapshot()
    det_snapshot = bot._determinize_snapshot(snapshot, obs, obs["player"])

    original_players = snapshot["players"]
    det_players = det_snapshot["players"]
    root_pid = obs["player"]

    assert det_players[root_pid]["hand"] == obs["hand"]
    assert det_players[root_pid]["drawn"] == obs.get("drawn")

    original_hidden = Counter()
    determinized_hidden = Counter()

    for pid, player in enumerate(original_players):
        if pid == root_pid:
            continue
        original_hidden.update(player.get("hand", []))
        determinized_hidden.update(det_players[pid].get("hand", []))
        original_drawn = player.get("drawn")
        det_drawn = det_players[pid].get("drawn")
        if original_drawn is not None:
            original_hidden.update([original_drawn])
            assert det_drawn is not None
            determinized_hidden.update([det_drawn])
        else:
            assert det_drawn is None
        assert len(det_players[pid].get("hand", [])) == len(player.get("hand", []))

    original_hidden.update(snapshot.get("wall", []))
    determinized_hidden.update(det_snapshot.get("wall", []))

    assert original_hidden == determinized_hidden
