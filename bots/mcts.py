"""Monte Carlo Tree Search bot implementation for Mahjong16."""

from __future__ import annotations

import copy
import math
import random
from collections import defaultdict
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
        pw_c: Progressive widening constant applied to visit counts.
        pw_alpha: Progressive widening exponent controlling growth of children.
        rave_k: Bias constant controlling the blend between Q and RAVE estimates.
    """

    simulations: int = 128
    rollout_depth: int = 6
    seed: Optional[int] = None
    puct_c: float = 1.4
    reuse_tree: bool = True
    virtual_loss: float = 0.0
    pw_c: float = 1.5
    pw_alpha: float = 0.5
    rave_k: float = 200.0


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

def _candidate_sort_key(action: Action, prior: float) -> Tuple[bool, int, float]:
    action_type = (action.get("type") or "").upper()
    is_pass = action_type == "PASS"
    priority = PRIORITY.get(action_type, 0)
    return (is_pass, -priority, -prior)


def _sort_candidates(
    candidates: Iterable[Tuple[Action, float]]
) -> List[Tuple[Action, float]]:
    return sorted(
        [(copy.deepcopy(action), prior) for action, prior in candidates],
        key=lambda item: _candidate_sort_key(item[0], item[1]),
    )


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
        "rave_stats",
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
        self.rave_stats: Dict[int, Tuple[float, int]] = {}
        self.children: Dict[int, "MCTSNode"] = {}
        self.unexpanded_actions: List[Tuple[Action, float]] = _sort_candidates(
            zip(legal_actions, priors),
        )

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
            self._simulate(root, root_snapshot, obs)

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
                new_unexpanded.append((action, prior))

        for key in list(candidate.children.keys()):
            if key not in legal_keys:
                del candidate.children[key]

        candidate.unexpanded_actions = _sort_candidates(new_unexpanded)
        if cached_player != player:
            self._reset_statistics(candidate)
        self._root_cache = candidate
        return candidate

    def _simulate(
        self, root: MCTSNode, snapshot: Dict[str, Any], root_obs: Observation
    ) -> None:
        det_snapshot = self._determinize_snapshot(snapshot, root_obs, root.player)
        env = Mahjong16Env.from_snapshot(self.env.rules, det_snapshot)
        node = root
        obs = env._obs(node.player)
        path = [node]

        while True:
            if getattr(env, "done", False):
                value = self._evaluate(env, root.player)
                self._backpropagate(path, value)
                return

            legal = obs.get("legal_actions", []) or env.legal_actions()
            self._refresh_node(node, obs, legal)

            if not legal:
                value = self._evaluate(env, root.player)
                self._backpropagate(path, value)
                return

            max_children = self._progressive_widening_limit(node)
            if node.unexpanded_actions and len(node.children) < max_children:
                action, prior = node.unexpanded_actions.pop(0)
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

            if not node.children:
                value = self._evaluate(env, root.player)
                self._backpropagate(path, value)
                return

            child = self._select_child(node)
            if child.action is None:
                if child.action_key is not None:
                    node.children.pop(child.action_key, None)
                continue
            obs, _, done, _ = env.step(copy.deepcopy(child.action))
            node = child
            path.append(node)
            if done:
                value = self._evaluate(env, root.player)
                self._backpropagate(path, value)
                return

    def _select_child(self, node: MCTSNode) -> MCTSNode:
        assert node.children, "select_child called on node without children"

        parent_visits = max(1, node.visits)
        sqrt_parent = math.sqrt(parent_visits)
        best_score = -float("inf")
        best_children: List[MCTSNode] = []

        for child in node.children.values():
            exploration = self.config.puct_c * child.prior * sqrt_parent / (1 + child.visits)
            rave_total, rave_visits = node.rave_stats.get(child.action_key or -1, (0.0, 0))
            q_rave = rave_total / rave_visits if rave_visits else 0.0
            beta_den = child.visits + rave_visits + self.config.rave_k
            beta = 0.0 if beta_den <= 0 else rave_visits / beta_den
            mixed_q = (1.0 - beta) * child.q + beta * q_rave
            score = mixed_q + exploration
            if score > best_score + 1e-12:
                best_score = score
                best_children = [child]
            elif math.isclose(score, best_score, rel_tol=1e-9, abs_tol=1e-12):
                best_children.append(child)

        return self.rng.choice(best_children)

    def _progressive_widening_limit(self, node: MCTSNode) -> int:
        if self.config.pw_c <= 0:
            return len(node.children) + len(node.unexpanded_actions)

        visits = max(1, node.visits)
        limit = int(self.config.pw_c * (visits ** self.config.pw_alpha))
        return max(1, limit)

    def _rollout(self, env: Mahjong16Env, obs: Observation, done: bool, root_player: int) -> float:
        depth = 0
        while not done and depth < self.config.rollout_depth:
            actions = obs.get("legal_actions", []) or env.legal_actions()
            if not actions:
                break
            action = self._rollout_policy(obs, actions)
            obs, _, done, _ = env.step(copy.deepcopy(action))
            depth += 1
        return self._evaluate(env, root_player)

    def _rollout_policy(self, obs: Observation, actions: Sequence[Action]) -> Action:
        phase = obs.get("phase")
        for action in actions:
            if (action.get("type") or "").upper() == "HU":
                return action

        if phase == "REACTION":
            return self._rollout_reaction_action(obs, actions)

        return self._rollout_turn_action(obs, actions)

    def _rollout_reaction_action(
        self, obs: Observation, actions: Sequence[Action]
    ) -> Action:
        pass_action = next(
            (a for a in actions if (a.get("type") or "").upper() == "PASS"),
            actions[0],
        )
        candidates = [
            a for a in actions if (a.get("type") or "").upper() != "PASS"
        ]
        if not candidates:
            return pass_action

        baseline = evaluate_heuristic(obs.get("hand") or [], obs.get("melds"))
        best_action = pass_action
        best_score: Tuple[int, float, int, float] = (
            0,
            0.0,
            0,
            -baseline.cost,
        )

        for action in candidates:
            action_type = (action.get("type") or "").upper()
            priority = PRIORITY.get(action_type, 0)
            hand, melds = self._simulate_claim_state(obs, action)
            snapshot = evaluate_heuristic(hand, melds)
            improvement = baseline.cost - snapshot.cost
            waits = len(action.get("waits") or [])
            score = (priority, improvement, waits, -snapshot.cost)
            if score > best_score:
                best_action = action
                best_score = score

        return best_action

    def _rollout_turn_action(self, obs: Observation, actions: Sequence[Action]) -> Action:
        tings = [a for a in actions if (a.get("type") or "").upper() == "TING"]
        if tings:
            return max(tings, key=lambda action: len(action.get("waits") or []))

        discards = [
            a for a in actions if (a.get("type") or "").upper() == "DISCARD"
        ]
        if not discards:
            return self.rng.choice(list(actions))

        baseline = evaluate_heuristic(obs.get("hand") or [], obs.get("melds"))
        best_action = discards[0]
        best_score: Optional[Tuple[float, int, int, float]] = None

        for action in discards:
            hand, melds = self._simulate_discard_state(obs, action)
            snapshot = evaluate_heuristic(hand, melds)
            improvement = baseline.cost - snapshot.cost
            danger = self._estimate_tile_danger(action.get("tile"))
            waits = len(action.get("waits") or [])
            score = (improvement, danger, waits, -snapshot.cost)
            if best_score is None or score > best_score:
                best_score = score
                best_action = action

        return best_action

    def _simulate_discard_state(
        self, obs: Observation, action: Action
    ) -> Tuple[List[int], List[dict]]:
        hand = list(obs.get("hand") or [])
        drawn = obs.get("drawn")
        melds = [copy.deepcopy(meld) for meld in (obs.get("melds") or [])]

        tile = action.get("tile")
        source = action.get("from", "hand")

        if source != "drawn":
            if tile in hand:
                hand.remove(tile)
            if drawn is not None:
                hand.append(drawn)
        else:
            # Discarding the drawn tile; it never entered the hand list.
            pass

        return hand, melds

    def _simulate_claim_state(
        self, obs: Observation, action: Action
    ) -> Tuple[List[int], List[dict]]:
        hand = list(obs.get("hand") or [])
        melds = [copy.deepcopy(meld) for meld in (obs.get("melds") or [])]
        last_discard = (obs.get("last_discard") or {})
        tile = last_discard.get("tile")
        claim_type = (action.get("type") or "").upper()

        if tile is None:
            return hand, melds

        if claim_type == "CHI":
            tiles = list(action.get("use") or [])
            for used in tiles:
                if used in hand:
                    hand.remove(used)
            melds.append({"type": "CHI", "tiles": tiles + [tile]})
        elif claim_type in {"PONG", "KONG", "GANG"}:
            needed = 2 if claim_type == "PONG" else 3
            removed = 0
            for idx in range(len(hand) - 1, -1, -1):
                if hand[idx] == tile:
                    hand.pop(idx)
                    removed += 1
                    if removed == needed:
                        break
            meld_size = needed + 1
            melds.append({"type": claim_type, "tiles": [tile] * meld_size})

        return hand, melds

    def _estimate_tile_danger(self, tile: Optional[int]) -> int:
        if tile is None:
            return 0
        if tile >= 27:
            return 3
        rank = tile % 9
        if rank in (0, 8):
            return 2
        if rank in (1, 7):
            return 1
        return 0

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
        seen_actions: Dict[int, set[int]] = defaultdict(set)
        for node in reversed(path):
            node.visits += 1
            node.w += value
            node.q = node.w / node.visits if node.visits else 0.0
            follow_up = seen_actions.get(node.player)
            if follow_up:
                for action_key in follow_up:
                    total, visits = node.rave_stats.get(action_key, (0.0, 0))
                    node.rave_stats[action_key] = (total + value, visits + 1)
            if node.action_key is not None:
                seen_actions[node.player].add(node.action_key)

    def _reset_statistics(self, node: MCTSNode) -> None:
        stack = [node]
        while stack:
            current = stack.pop()
            current.visits = 0
            current.w = 0.0
            current.q = 0.0
            current.rave_stats.clear()
            stack.extend(current.children.values())

    def _refresh_node(self, node: MCTSNode, obs: Observation, legal_actions: Sequence[Action]) -> None:
        phase = obs.get("phase", node.phase)
        player = obs.get("player", node.player)
        node.phase = phase
        node.player = player

        if not legal_actions:
            node.unexpanded_actions = []
            node.children.clear()
            return

        priors = self.policy_prior(phase, legal_actions)
        legal_keys: set[int] = set()
        fresh_unexpanded: List[Tuple[Action, float]] = []

        for action, prior in zip(legal_actions, priors):
            key = _encode_action_key(action, self._action_table)
            legal_keys.add(key)
            if key in node.children:
                child = node.children[key]
                child.parent = node
                child.prior = prior
                child.action = copy.deepcopy(action)
                child.action_key = key
            else:
                fresh_unexpanded.append((action, prior))

        for key in list(node.children.keys()):
            if key not in legal_keys:
                del node.children[key]

        node.unexpanded_actions = _sort_candidates(fresh_unexpanded)

    # ------------------------------------------------------------------
    # Determinization helpers

    def _determinize_snapshot(
        self, snapshot: Dict[str, Any], obs: Observation, root_player: int
    ) -> Dict[str, Any]:
        det_snapshot = copy.deepcopy(snapshot)
        players = det_snapshot.get("players", [])
        if not players:
            return det_snapshot

        original_players = snapshot.get("players", [])
        hand_sizes = [len(p.get("hand", [])) for p in original_players]
        had_drawn = [p.get("drawn") is not None for p in original_players]

        hidden_tiles: List[int] = []
        wall_tiles = list(det_snapshot.get("wall", []) or [])
        wall_len = len(wall_tiles)
        det_snapshot["wall"] = []

        forced_tiles: Dict[int, List[int]] = defaultdict(list)
        last_discard = snapshot.get("last_discard") or {}
        discard_tile = last_discard.get("tile")
        for claim in snapshot.get("claims", []) or []:
            pid = claim.get("pid")
            if pid is None:
                continue
            claim_type = (claim.get("type") or "").upper()
            if claim_type == "CHI":
                forced_tiles[pid].extend(claim.get("use") or [])
            elif claim_type == "PONG" and discard_tile is not None:
                forced_tiles[pid].extend([discard_tile, discard_tile])
            elif claim_type in {"KONG", "GANG"} and discard_tile is not None:
                forced_tiles[pid].extend([discard_tile] * 3)

        for idx, player in enumerate(players):
            if idx == root_player:
                player["hand"] = list(obs.get("hand") or [])
                player["drawn"] = obs.get("drawn")
                continue
            hidden_tiles.extend(player.get("hand") or [])
            player["hand"] = []
            drawn_tile = player.get("drawn")
            if drawn_tile is not None:
                hidden_tiles.append(drawn_tile)
            player["drawn"] = None

        hidden_tiles.extend(wall_tiles)
        self.rng.shuffle(hidden_tiles)

        available_tiles = hidden_tiles

        for idx, player in enumerate(players):
            if idx == root_player:
                continue
            hand_len = hand_sizes[idx]
            forced = list(forced_tiles.get(idx, []))
            assigned_hand: List[int] = []
            for tile in forced[:hand_len]:
                try:
                    available_tiles.remove(tile)
                except ValueError as exc:
                    raise RuntimeError("forced tile missing during determinization") from exc
                assigned_hand.append(tile)
            remaining = hand_len - len(assigned_hand)
            if remaining > 0:
                assigned_hand.extend(available_tiles[:remaining])
                del available_tiles[:remaining]
            self.rng.shuffle(assigned_hand)
            player["hand"] = assigned_hand
            if had_drawn[idx]:
                if not available_tiles:
                    raise RuntimeError("insufficient tiles while determinizing drawn states")
                player["drawn"] = available_tiles.pop(0)
            else:
                player["drawn"] = None

        if len(available_tiles) < wall_len:
            raise RuntimeError("insufficient tiles while determinizing hidden state")
        det_snapshot["wall"] = list(available_tiles[:wall_len])
        del available_tiles[:wall_len]
        return det_snapshot

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
