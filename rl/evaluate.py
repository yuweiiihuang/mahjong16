"""Paired, player-visible evaluation against three fixed opponents."""
from __future__ import annotations

import argparse
import json
import random
from math import sqrt
from pathlib import Path
from statistics import mean, stdev
from time import perf_counter

import torch

from app.hand_store import write_private_record
from app.runtime import SessionService
from app.table import TableManager
from bots.greedy import GreedyBotStrategy
from bots.policies import AutoStrategy, Strategy
from domain.gameplay.game_env import MahjongEnvironment
from domain.rules.ruleset import Ruleset
from domain.scoring.lookup import load_scoring_assets
from rl.encoding import encode
from rl.env import LearnerEpisode, observation, training_spec
from rl.net import PolicyValueNet, load_checkpoint
from rl.selfplay import hand_seed


class _RandomStrategy:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def choose(self, obs: dict) -> dict:
        """Sample all legal actions uniformly, including optional wins and passes."""
        return self.rng.choice(obs["legal_actions"])


def _rank(payments: list[int], learner: int) -> float:
    """Use midranks for ties instead of introducing a seat-based tiebreak."""
    score = payments[learner]
    return 1 + sum(p > score for p in payments) + (payments.count(score) - 1) / 2


class _VisibleStrategy:
    def __init__(self, env: MahjongEnvironment, policy: Strategy) -> None:
        self.env = env
        self.policy = policy

    def choose(self, obs: dict) -> dict:
        """Replace runtime observations with the established visible-player contract."""
        visible = observation(self.env, obs["player"])
        action = self.policy.choose(visible)
        if action not in visible["legal_actions"]:
            raise ValueError("Policy selected an illegal match action")
        return action


class _BoundedMatch(SessionService):
    def _play_single_hand(self, hand_idx: int) -> bool:
        if hand_idx > 512:
            raise RuntimeError("Match exceeded 512 hands; no complete result is published")
        return super()._play_single_hand(hand_idx)

    def _process_hand_end(self, hand_idx: int) -> bool:
        complete = super()._process_hand_end(hand_idx)
        self.hand_summaries[-1]["flower_win_type"] = self.env.flower_win_type
        return complete


def _play_match(seed: int, learner: int, policy: Strategy, fixed: Strategy,
                rules: Ruleset) -> tuple[list[dict], list[int]]:
    """Run one full jang using the existing dealer, draw and wind progression."""
    env = MahjongEnvironment(rules, seed=seed)
    table = load_scoring_assets(rules.scoring_profile, rules.scoring_overrides_path)
    strategies = [_VisibleStrategy(env, policy if pid == learner else fixed) for pid in range(4)]
    session = _BoundedMatch(env=env, table_manager=TableManager(rules, seed=seed),
                            strategies=strategies, scoring_assets=table, jangs=1)
    initial = list(session.totals)
    summaries = session.run()
    net = [after - before for after, before in zip(session.totals, initial)]
    if sum(net) != 0:
        raise RuntimeError("Non-zero-sum match settlement")
    return summaries, net


def _hand_result(seed: int, learner: int, payments: list[int], *, winner: int | None,
                 win_source: str | None, discarder: int | None, dealer: int,
                 flower_win_type: str | None = None) -> dict:
    return {"seed": seed, "learner": learner, "payment": payments[learner],
            "rank": _rank(payments, learner), "winner": winner, "win_source": win_source,
            "discarder": discarder, "dealer": dealer, "flower_win_type": flower_win_type}


def evaluate(candidates: list[str], *, walls: int = 100, start: int = 500_000_000,
             split: str = "validation", opponent: str = "greedy",
             unit: str = "hand", rules: Ruleset | None = None) -> dict:
    """Evaluate hands or complete jangs, rotating all seats for each independent seed."""
    if (walls <= 0 or start < 500_000_000 or start + walls > 1_000_000_000
            or split not in ("validation", "test") or not candidates
            or len(set(candidates)) != len(candidates) or opponent not in ("greedy", "auto")
            or unit not in ("hand", "jang")):
        raise ValueError("Invalid evaluation candidates, split or wall range")
    rules = rules or Ruleset()
    began = perf_counter()
    spec = training_spec(rules)
    first = LearnerEpisode(hand_seed(split, start), 0, rules)
    state, actions = encode(first.current()) if first.current() else (None, None)
    policies = {}
    for name in candidates:
        if name == "greedy":
            policies[name] = GreedyBotStrategy()
        elif name == "random":
            policies[name] = None
        elif name == "untrained":
            if state is None:
                raise ValueError("Choose an evaluation start with a non-terminal first hand")
            torch.manual_seed(0)
            policies[name] = PolicyValueNet(len(state), len(actions[0]))
        else:
            policies[name] = load_checkpoint(Path(name), spec)[0]
    results = {name: [] for name in candidates}
    matches = {name: [] for name in candidates}
    for index in range(start, start + walls):
        for seat in range(4):
            for name, policy in policies.items():
                fixed = GreedyBotStrategy() if opponent == "greedy" else AutoStrategy()
                seed = hand_seed(split, index)
                if name == "random":
                    policy = _RandomStrategy(4 * seed + seat)
                if unit == "jang":
                    summaries, totals = _play_match(seed, seat, policy, fixed, rules)
                    matches[name].append({"seed": seed, "learner": seat,
                                          "payment": totals[seat], "rank": _rank(totals, seat),
                                          "hands": len(summaries)})
                    for hand in summaries:
                        row = _hand_result(
                            seed, seat, hand["payments"], winner=hand["winner"],
                            win_source=hand.get("win_source"), discarder=hand.get("ron_from"),
                            dealer=hand["dealer_pid"], flower_win_type=hand.get("flower_win_type"))
                        row["hand_index"] = hand["hand_index"]
                        results[name].append(row)
                    continue
                episode = LearnerEpisode(seed, seat, rules, opponent=fixed)
                while (obs := episode.current()) is not None:
                    episode.step(policy.choose(obs))
                env = episode.env
                row = _hand_result(seed, seat, episode.payments(), winner=env.winner,
                                   win_source=env.win_source, discarder=env.turn_at_win,
                                   dealer=env.dealer_pid, flower_win_type=env.flower_win_type)
                row["engine_steps"] = episode.steps
                results[name].append(row)
    summary = {}
    comparison = matches if unit == "jang" else results
    clusters = {name: [mean(r["payment"] for r in rows[i:i + 4])
                       for i in range(0, len(rows), 4)] for name, rows in comparison.items()}
    for name, rows in results.items():
        summary[name] = {
            "hands": len(rows), "seed_groups": walls, "matches": len(matches[name]),
            "mean_hand_net_payment": mean(r["payment"] for r in rows),
            "mean_match_net_payment": mean(clusters[name]) if unit == "jang" else None,
            "mean_rank": mean(r["rank"] for r in comparison[name]), "rank_unit": unit,
            "seed_group_standard_error": stdev(clusters[name]) / sqrt(walls)
            if walls > 1 else None,
            "win_rate": mean(r["winner"] == r["learner"] for r in rows),
            "draw_rate": mean(r["winner"] is None for r in rows),
            "deal_in_rate": mean(r["winner"] != r["learner"] and r["winner"] is not None
                                 and r["win_source"] == "RON"
                                 and r["flower_win_type"] is None
                                 and r["discarder"] == r["learner"] for r in rows),
            "seat_payment": [mean(r["payment"] for r in rows if r["learner"] == seat)
                             for seat in range(4)],
            "dealer_payment": mean(r["payment"] for r in rows if r["learner"] == r["dealer"]),
            "nondealer_payment": mean(r["payment"] for r in rows
                                      if r["learner"] != r["dealer"]),
        }
        if "greedy" in clusters and name != "greedy":
            differences = [a - b for a, b in zip(clusters[name], clusters["greedy"])]
            summary[name]["paired_vs_greedy"] = {
                "mean": mean(differences),
                "seed_group_standard_error": stdev(differences) / sqrt(walls)
                if walls > 1 else None,
            }
    return {"evaluation_version": 2, "spec": spec, "split": split, "start": start,
            "opponent": opponent, "rank_ties": "average",
            "unit": unit, "comparison_unit": unit,
            "inference": ("uniform_all_legal" if candidates == ["random"] else
                          "mixed" if "random" in candidates else "argmax"),
            "random_sampling": {"actions": "uniform_all_legal", "seed": "4 * seed + seat"}
            if "random" in candidates else None,
            "summary": summary, "hands": results, "matches": matches,
            "seconds": perf_counter() - began}


def main() -> None:
    """Evaluate saved models without using test results for checkpoint selection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", nargs="+",
                        help="random, greedy, untrained, or checkpoint paths")
    parser.add_argument("--walls", type=int, default=100,
                        help="independent seed groups; four seats per hand or match seed")
    parser.add_argument("--start", type=int, default=500_000_000)
    parser.add_argument("--split", choices=("validation", "test"), default="validation")
    parser.add_argument("--opponent", choices=("greedy", "auto"), default="greedy")
    parser.add_argument("--unit", choices=("hand", "jang"), default="hand",
                        help="jang is one complete four-wind match, including repeat dealers")
    parser.add_argument("--output", type=Path, required=True)
    args = vars(parser.parse_args())
    output = args.pop("output")
    if output.exists():
        raise FileExistsError(output)
    torch.set_num_threads(1)
    result = evaluate(**args)
    write_private_record(output, result)
    print(json.dumps(result["summary"]))


if __name__ == "__main__":
    main()
