"""Monte Carlo Tree Search bot implementation for Mahjong16."""

from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from bots.heuristics import HeuristicSnapshot, heuristic as evaluate_heuristic
from core.env import PRIORITY, Mahjong16Env


Action = Dict[str, Any]
Observation = Dict[str, Any]


@dataclass(frozen=True)
class MCTSBotConfig:
    """Configuration options for :class:`MCTSBot`.

    Attributes:
        simulations: Number of playouts performed per decision.
        rollout_depth: Maximum depth for rollout simulations.
        seed: Optional RNG seed used for deterministic behaviour.
        puct_c: Exploration constant for the PUCT selection formula.
        reuse_tree: Whether to reuse the previous search tree between turns.
        virtual_loss: Virtual loss used to support speculative parallel playouts.
    """

    simulations: int = 128
    rollout_depth: int = 12
    seed: Optional[int] = None
    puct_c: float = 1.4
    reuse_tree: bool = True
    virtual_loss: float = 0.0


def _freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze_value(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(_freeze_value(v) for v in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_value(v) for v in value))
    return value


def _encode_action_key(action: Action, table: Dict[Tuple[Tuple[str, Any], ...], int]) -> int:
    """Return a stable integer identifier for the given action."""

    frozen = tuple(sorted((k, _freeze_value(v)) for k, v in action.items()))
    if frozen not in table:
        table[frozen] = len(table)
    return table[frozen]


def _copy_actions(actions: Iterable[Action]) -> List[Action]:
    return [copy.deepcopy(a) for a in actions]


class MCTSNode:
    """Single node within the MCTS search tree."""

    __slots__ = (
        "player",
        "phase",
        "action",
        "action_key",
        "parent",
        "visits",
        "prior",
        "w",
        "q",
        "children",
        "unexpanded_actions",
    )

    def __init__(
        self,
        *,
        player: int,
        phase: str,
        legal_actions: Sequence[Action],
        priors: Sequence[float],
        action: Optional[Action] = None,
        action_key: Optional[int] = None,
        parent: Optional["MCTSNode"] = None,
        prior: float = 1.0,
    ) -> None:
        if len(priors) != len(legal_actions):
            raise ValueError("priors must match legal_actions length")
        self.player = player
        self.phase = phase
        self.action = copy.deepcopy(action) if action is not None else None
        self.action_key = action_key
        self.parent = parent
        self.visits = 0
        self.prior = prior
        self.w = 0.0
        self.q = 0.0
        self.children: Dict[int, "MCTSNode"] = {}
        self.unexpanded_actions: List[Tuple[Action, float]] = [
            (copy.deepcopy(act), pri)
            for act, pri in zip(_copy_actions(legal_actions), priors)
        ]

    def is_terminal(self) -> bool:
        return not self.unexpanded_actions and not self.children


class MCTSBot:
    """Monte Carlo Tree Search bot for Mahjong16.

    The bot clones the provided environment and performs simulated playouts
    before choosing an action. The :class:`MCTSBotConfig` allows tuning the
    number of simulations, the PUCT exploration constant, tree reuse
    behaviour, and the rollout horizon. Provide an optional seed for
    deterministic behaviour.
    """

    def __init__(self, env: Mahjong16Env, config: Optional[MCTSBotConfig] = None) -> None:
        self.env = env
        self.config = config or MCTSBotConfig()
        self.rng = random.Random(self.config.seed)
        self._action_table: Dict[Tuple[Tuple[str, Any], ...], int] = {}
        self._root_cache: Optional[MCTSNode] = None
        self._last_action_key: Optional[int] = None
        self._root_snapshot: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API

    def choose(self, obs: Observation) -> Action:
        """Choose an action using Monte Carlo Tree Search."""

        actions: List[Action] = obs.get("legal_actions", []) or []
        if not actions:
            return {"type": "PASS"}

        for action in actions:
            if (action.get("type") or "").upper() == "HU":
                return copy.deepcopy(action)

        if len(actions) == 1:
            return copy.deepcopy(actions[0])

        root, root_snapshot = self._prepare_root(obs, actions)

        for _ in range(max(1, self.config.simulations)):
            self._simulate(root, root_snapshot)

        if not root.children:
            self._root_cache = root
            self._last_action_key = None
            return copy.deepcopy(actions[0])

        best_child = max(
            root.children.values(),
            key=lambda node: (node.visits, node.q),
        )

        self._root_cache = root
        self._last_action_key = best_child.action_key
        return copy.deepcopy(best_child.action or actions[0])

    # ------------------------------------------------------------------
    # Core MCTS steps

    def _prepare_root(self, obs: Observation, actions: Sequence[Action]) -> Tuple[MCTSNode, Dict[str, Any]]:
        snapshot = self.env.snapshot()
        player = obs.get("player", 0)
        phase = obs.get("phase", "TURN")
        priors = self.policy_prior(phase, actions)

        if self.config.reuse_tree and self._root_cache is not None:
            root = self._reuse_root(player, phase, actions, priors)
        else:
            root = MCTSNode(
                player=player,
                phase=phase,
                legal_actions=actions,
                priors=priors,
            )

        self._root_snapshot = snapshot
        return root, snapshot

    def _reuse_root(
        self,
        player: int,
        phase: str,
        actions: Sequence[Action],
        priors: Sequence[float],
    ) -> MCTSNode:
        assert self._root_cache is not None
        node = self._root_cache
        candidate = node
        if self._last_action_key is not None and self._last_action_key in candidate.children:
            candidate = candidate.children[self._last_action_key]

        cached_player = candidate.player
        candidate.parent = None
        candidate.player = player
        candidate.phase = phase
        candidate.action = None
        candidate.action_key = None
        candidate.prior = 1.0

        legal_keys: set[int] = set()
        new_unexpanded: List[Tuple[Action, float]] = []
        for action, prior in zip(actions, priors):
            key = _encode_action_key(action, self._action_table)
            legal_keys.add(key)
            if key in candidate.children:
                child = candidate.children[key]
                child.prior = prior
                child.parent = candidate
                child.action = copy.deepcopy(action)
                child.action_key = key
            else:
                new_unexpanded.append((copy.deepcopy(action), prior))

        for key in list(candidate.children.keys()):
            if key not in legal_keys:
                del candidate.children[key]

        candidate.unexpanded_actions = new_unexpanded
        if cached_player != player:
            self._reset_statistics(candidate)
        self._root_cache = candidate
        return candidate

    def _simulate(self, root: MCTSNode, snapshot: Dict[str, Any]) -> None:
        env = Mahjong16Env.from_snapshot(self.env.rules, snapshot)
        node = root
        obs = env._obs(node.player)
        path = [node]

        while True:
            if getattr(env, "done", False) or node.is_terminal():
                value = self._evaluate(env, root.player)
                self._backpropagate(path, value)
                return

            if node.unexpanded_actions:
                idx = self._sample_unexpanded(node.unexpanded_actions)
                action, prior = node.unexpanded_actions.pop(idx)
                obs, _, done, _ = env.step(copy.deepcopy(action))
                legal = obs.get("legal_actions", []) or env.legal_actions()
                priors = self.policy_prior(obs.get("phase", "TURN"), legal)
                key = _encode_action_key(action, self._action_table)
                child = MCTSNode(
                    player=obs.get("player", root.player),
                    phase=obs.get("phase", "TURN"),
                    legal_actions=legal,
                    priors=priors,
                    action=action,
                    action_key=key,
                    parent=node,
                    prior=prior,
                )
                node.children[key] = child
                path.append(child)
                value = self._rollout(env, obs, done, root.player)
                self._backpropagate(path, value)
                return

            child = self._select_child(node)
            next_action = copy.deepcopy(child.action) if child.action is not None else {"type": "PASS"}
            obs, _, done, _ = env.step(next_action)
            node = child
            path.append(node)
            if done:
                value = self._evaluate(env, root.player)
                self._backpropagate(path, value)
                return

    def _sample_unexpanded(self, unexpanded: Sequence[Tuple[Action, float]]) -> int:
        if not unexpanded:
            raise ValueError("cannot sample from empty unexpanded set")

        weights = [max(prior, 0.0) for _action, prior in unexpanded]
        total = sum(weights)
        if total <= 0.0:
            return self.rng.randrange(len(unexpanded))

        threshold = self.rng.random() * total
        cumulative = 0.0
        for idx, weight in enumerate(weights):
            cumulative += weight
            if threshold <= cumulative:
                return idx
        return len(unexpanded) - 1

    def _select_child(self, node: MCTSNode) -> MCTSNode:
        assert node.children, "select_child called on node without children"

        parent_visits = max(1, node.visits)
        sqrt_parent = math.sqrt(parent_visits)
        best_score = -float("inf")
        best_children: List[MCTSNode] = []

        for child in node.children.values():
            exploration = self.config.puct_c * child.prior * sqrt_parent / (1 + child.visits)
            score = child.q + exploration
            if score > best_score + 1e-12:
                best_score = score
                best_children = [child]
            elif math.isclose(score, best_score, rel_tol=1e-9, abs_tol=1e-12):
                best_children.append(child)

        return self.rng.choice(best_children)

    def _rollout(self, env: Mahjong16Env, obs: Observation, done: bool, root_player: int) -> float:
        depth = 0
        while not done and depth < self.config.rollout_depth:
            actions = obs.get("legal_actions", []) or env.legal_actions()
            if not actions:
                break
            action = self._rollout_policy(obs.get("phase"), actions)
            obs, _, done, _ = env.step(action)
            depth += 1
        return self._evaluate(env, root_player)

    def _rollout_policy(self, phase: Optional[str], actions: Sequence[Action]) -> Action:
        for action in actions:
            if (action.get("type") or "").upper() == "HU":
                return action

        if phase == "REACTION":
            candidates = [a for a in actions if (a.get("type") or "").upper() != "PASS"]
            if candidates:
                candidates.sort(key=lambda a: PRIORITY.get((a.get("type") or "").upper(), -1), reverse=True)
                return candidates[0]
            return actions[0]

        discards = [a for a in actions if (a.get("type") or "").upper() == "DISCARD"]
        if discards:
            return self.rng.choice(discards)
        return self.rng.choice(list(actions))

    def _evaluate(self, env: Mahjong16Env, root_player: int) -> float:
        if getattr(env, "done", False):
            winner = getattr(env, "winner", None)
            if winner is None:
                return 0.0
            if winner == root_player:
                return 1.0
            return -1.0

        pov = env._obs(root_player)
        hand = list(pov.get("hand") or [])
        drawn = pov.get("drawn")
        if drawn is not None:
            hand.append(drawn)
        snapshot: HeuristicSnapshot = evaluate_heuristic(hand, pov.get("melds"))
        # Convert heuristic cost into a bounded score in [-1, 1]
        value = -snapshot.cost / 10.0
        value += snapshot.melds * 0.05
        if snapshot.has_pair:
            value += 0.05
        return max(-1.0, min(1.0, value))

    def _backpropagate(self, path: Sequence[MCTSNode], value: float) -> None:
        for node in reversed(path):
            node.visits += 1
            node.w += value
            node.q = node.w / node.visits if node.visits else 0.0

    def _reset_statistics(self, node: MCTSNode) -> None:
        stack = [node]
        while stack:
            current = stack.pop()
            current.visits = 0
            current.w = 0.0
            current.q = 0.0
            stack.extend(current.children.values())

    # ------------------------------------------------------------------
    # Policy helpers

    def policy_prior(self, phase: Optional[str], actions: Sequence[Action]) -> List[float]:
        if not actions:
            return []

        weights: List[float] = []
        for action in actions:
            action_type = (action.get("type") or "").upper()
            weight = 1.0
            if action_type == "HU":
                weight = 8.0
            elif phase == "REACTION":
                priority = PRIORITY.get(action_type, 0)
                weight = max(0.1, 1.0 + priority)
            elif action_type in {"PONG", "CHI"}:
                weight = 2.0
            elif action_type in {"KONG", "BU_KONG", "AN_KONG"}:
                weight = 3.0
            elif action_type == "PASS":
                weight = 0.5
            weights.append(weight)

        total = sum(weights)
        if total <= 0.0:
            uniform = 1.0 / len(actions)
            return [uniform for _ in actions]

        return [weight / total for weight in weights]


__all__ = ["MCTSBot", "MCTSBotConfig"]
