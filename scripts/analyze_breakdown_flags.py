"""Analyze breakdown flag frequencies from Mahjong16 log CSV files."""
from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

# Ensure the project root is importable when running as a loose script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domain.scoring.lookup import load_scoring_assets

DEFAULT_SCORING_JSON = (
    Path(__file__).resolve().parent.parent / "configs" / "scoring" / "profiles" / "taiwan_base.json"
)
DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def load_flag_sequence(scoring_path: Path, profile: str) -> tuple[list[str], Mapping[str, str]]:
    table = load_scoring_assets(profile, str(scoring_path))
    # Preserve insertion order from JSON by iterating over dict keys directly.
    return list(table.values.keys()), table.labels


def iter_breakdown_flags(csv_path: Path) -> Iterable[set[str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if "breakdown_tags" not in reader.fieldnames:
            raise ValueError("CSV missing 'breakdown_tags' column")
        for row in reader:
            raw_tags = row.get("breakdown_tags", "") or ""
            if not raw_tags:
                continue
            tags = set()
            for token in raw_tags.split("|"):
                token = token.strip()
                if not token:
                    continue
                key, *_ = token.split("=", 1)
                tags.add(key)
            if tags:
                yield tags


def compute_flag_frequencies(rows: Iterable[set[str]], ordered_flags: list[str]) -> tuple[Counter[str], int]:
    counts: Counter[str] = Counter()
    total = 0
    for tags in rows:
        total += 1
        counts.update(tags)
    # Ensure all flags exist in counter so downstream formatting can rely on zero entries.
    for flag in ordered_flags:
        counts.setdefault(flag, 0)
    return counts, total


def format_results(
    counts: Mapping[str, int], total: int, ordered_flags: list[str], labels: Mapping[str, str]
) -> str:
    lines = []
    lines.append(f"Total hands with breakdown tags: {total}")

    def display_width(text: str) -> int:
        width = 0
        for ch in text:
            east = unicodedata.east_asian_width(ch)
            width += 2 if east in {"F", "W"} else 1
        return width

    max_label_width = max((display_width(str(labels.get(flag, flag))) for flag in ordered_flags), default=0)

    def pad_label(text: str) -> str:
        current = display_width(text)
        padding = max_label_width - current
        return f"{text}{' ' * padding}"

    for flag in ordered_flags:
        occur = counts.get(flag, 0)
        ratio = (occur / total * 100) if total else 0.0
        label = str(labels.get(flag, flag))
        lines.append(f"{pad_label(label)}  {occur:>6} ({ratio:6.2f}%)")
    return "\n".join(lines)


def find_latest_csv(log_dir: Path) -> Path:
    candidates = [path for path in log_dir.rglob("*.csv") if path.is_file()]
    if not candidates:
        raise SystemExit(f"No CSV files found under logs directory: {log_dir}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, nargs="?", help="Path to log CSV file")
    parser.add_argument(
        "--scoring-json",
        type=Path,
        default=DEFAULT_SCORING_JSON,
        help="Scoring config JSON that defines flag order (default: configs/scoring/profiles/taiwan_base.json)",
    )
    parser.add_argument(
        "--profile",
        default="taiwan_base",
        help="Scoring profile key to pull flag order from (default: taiwan_base)",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="Optional subset of flags to display; respects JSON ordering",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path: Path | None = args.csv
    scoring_path: Path = args.scoring_json
    if csv_path is None:
        if not DEFAULT_LOG_DIR.exists():
            raise SystemExit("Log directory not found and no CSV provided")
        csv_path = find_latest_csv(DEFAULT_LOG_DIR)
        print(f"Using latest log CSV: {csv_path}", file=sys.stderr)
    assert csv_path is not None
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")
    if not scoring_path.exists():
        raise SystemExit(f"Scoring JSON not found: {scoring_path}")

    ordered_flags, labels = load_flag_sequence(scoring_path, args.profile)
    if args.only:
        requested = set(args.only)
        ordered_flags = [flag for flag in ordered_flags if flag in requested]
        missing = requested.difference(ordered_flags)
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise SystemExit(f"Requested flag(s) not in profile order: {missing_str}")

    counts, total = compute_flag_frequencies(iter_breakdown_flags(csv_path), ordered_flags)
    print(format_results(counts, total, ordered_flags, labels))


if __name__ == "__main__":
    main()
