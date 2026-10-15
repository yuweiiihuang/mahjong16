"""Generate versioned Greedy demonstrations without storing private engine state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from app.hand_store import open_private_record
from bots.greedy import GreedyBotStrategy
from domain.rules.ruleset import Ruleset
from rl.encoding import ENCODING_VERSION
from rl.env import HandEpisode, training_spec

SPLIT_BASE = {"train": 0, "validation": 1_000_000_000, "test": 2_000_000_000}


def hand_seed(split: str, index: int) -> int:
    """Allocate non-overlapping demonstration and PPO streams within each split."""
    if split not in SPLIT_BASE or not 0 <= index < 1_000_000_000:
        raise ValueError("Invalid split or hand index")
    return SPLIT_BASE[split] + index


def generate(path: Path, hands: int, *, split: str, start: int = 0,
             rules: Ruleset | None = None) -> dict:
    """Write actual actor decisions; a failed hand never publishes a partial dataset."""
    if hands <= 0 or start < 0 or start + hands > 500_000_000:
        raise ValueError("Invalid demonstration range")
    rules = rules or Ruleset()
    began = perf_counter()
    spec = training_spec(rules)
    teacher = GreedyBotStrategy()
    counts = {"hands": hands, "decisions": 0, "choices": 0, "actions": {}}
    with open_private_record(path) as handle:
        header = {"dataset_version": 1, "encoding_version": ENCODING_VERSION, "spec": spec,
                  "split": split, "start": start, "hands": hands}
        handle.write(json.dumps(header) + "\n")
        for index in range(start, start + hands):
            seed = hand_seed(split, index)
            episode = HandEpisode(seed, rules)
            while (obs := episode.current()) is not None:
                action = teacher.choose(obs)
                label = obs["legal_actions"].index(action)
                row = {"seed": seed, "seq": episode.steps, "observation": obs, "label": label}
                handle.write(json.dumps(row) + "\n")
                counts["decisions"] += 1
                counts["choices"] += len(obs["legal_actions"]) > 1
                kind = action["type"]
                counts["actions"][kind] = counts["actions"].get(kind, 0) + 1
                episode.act(action)
            episode.payments()
    counts["seconds"] = perf_counter() - began
    return counts


def main() -> None:
    """Collect local demonstrations; output must not already exist."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--hands", type=int, default=100)
    parser.add_argument("--split", choices=SPLIT_BASE, required=True)
    parser.add_argument("--start", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(generate(args.output, args.hands, split=args.split, start=args.start)))


if __name__ == "__main__":
    main()
