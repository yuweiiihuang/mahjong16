#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    zh_name: str
    source_doc: str
    required_in_taiwan_base: bool
    tai_value: int
    trigger: str
    excludes: list[str]
    includes: list[str]
    status: str


@dataclass(frozen=True)
class RuleCoverageItem:
    rule_id: str
    zh_name: str
    spec_required: bool
    in_profile: bool
    in_engine: bool
    in_tests: bool
    gap_level: str
    notes: str


@dataclass(frozen=True)
class CoverageSummary:
    total_rules: int
    required_rules: int
    covered_required_rules: int
    gaps_by_level: dict[str, int]


ACC_ADD_PATTERN = re.compile(r'acc\.add\("([a-z0-9_]+)"')


FLOW_RULE_DETECTORS: dict[str, tuple[str, ...]] = {
    "si_gang_pai": ("四槓", "si_gang", "four_kong", "four gang"),
    "zha_hu_penalty": ("詐胡", "zha_hu", "illegal hu", "false hu", "penalty"),
    "dealer_streak_cap_10": ("dealer_streak", "min(10", "<= 10", "cap"),
}


FLOW_RULE_TEST_TOKENS: dict[str, tuple[str, ...]] = {
    "si_gang_pai": ("四槓", "si_gang", "four_kong", "four gang"),
    "zha_hu_penalty": ("詐胡", "zha_hu", "illegal hu", "false hu"),
    "dealer_streak_cap_10": ("連莊上限", "上限十次", "cap_10"),
}


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _split_tokens(value: str) -> list[str]:
    if not value:
        return []
    return [token.strip() for token in value.split(";") if token.strip()]


def load_rule_catalog(path: Path) -> list[RuleSpec]:
    with path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        rows: list[RuleSpec] = []
        for row in reader:
            rule_id = (row.get("rule_id") or "").strip()
            if not rule_id:
                continue
            rows.append(
                RuleSpec(
                    rule_id=rule_id,
                    zh_name=(row.get("zh_name") or "").strip(),
                    source_doc=(row.get("source_doc") or "").strip(),
                    required_in_taiwan_base=_parse_bool(row.get("required_in_taiwan_base") or ""),
                    tai_value=_parse_int(row.get("tai_value") or "0"),
                    trigger=(row.get("trigger") or "").strip(),
                    excludes=_split_tokens((row.get("excludes") or "").strip()),
                    includes=_split_tokens((row.get("includes") or "").strip()),
                    status=(row.get("status") or "").strip() or "unknown",
                )
            )
    return rows


def load_profiles(profiles_dir: Path) -> dict[str, dict[str, int]]:
    profiles: dict[str, dict[str, int]] = {}
    for path in sorted(profiles_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        if isinstance(payload, dict):
            normalized: dict[str, int] = {}
            for key, value in payload.items():
                try:
                    normalized[str(key)] = int(value)
                except Exception:
                    normalized[str(key)] = 0
            profiles[path.stem] = normalized
    return profiles


def scan_engine_keys(scoring_rules_dir: Path) -> set[str]:
    keys: set[str] = set()
    for path in sorted(scoring_rules_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in ACC_ADD_PATTERN.findall(text):
            keys.add(match)
    return keys


def read_text_map(paths: Iterable[Path]) -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in sorted(paths)}


def detect_flow_rule(rule_id: str, text_map: dict[Path, str]) -> bool:
    tokens = FLOW_RULE_DETECTORS.get(rule_id)
    if not tokens:
        return False
    corpus = "\n".join(text_map.values()).lower()
    matched = [token.lower() in corpus for token in tokens]
    if rule_id == "dealer_streak_cap_10":
        return all(matched)
    return any(matched)


def detect_tests(rule_id: str, test_map: dict[Path, str]) -> bool:
    token = rule_id
    pattern = re.compile(rf"\b{re.escape(token)}\b")
    corpus = "\n".join(test_map.values())
    if pattern.search(corpus):
        return True

    flow_tokens = FLOW_RULE_TEST_TOKENS.get(rule_id)
    if flow_tokens:
        lower = corpus.lower()
        return any(token.lower() in lower for token in flow_tokens)
    return False


def gap_level_for(spec_required: bool, profile_relevant: bool, in_profile: bool, in_engine: bool, in_tests: bool) -> str:
    if spec_required and profile_relevant and not in_profile:
        return "P0"
    if spec_required and not in_engine:
        return "P0"
    if (not spec_required) and (not in_engine):
        return "P2"
    if in_engine and (not in_tests):
        return "P3"
    return ""


def build_coverage(
    specs: list[RuleSpec],
    profiles: dict[str, dict[str, int]],
    taiwan_profile: str,
    engine_keys: set[str],
    gameplay_map: dict[Path, str],
    test_map: dict[Path, str],
) -> tuple[list[RuleCoverageItem], CoverageSummary]:
    taiwan_keys = set(profiles.get(taiwan_profile, {}).keys())
    profile_union: set[str] = set()
    for table in profiles.values():
        profile_union.update(table.keys())

    items: list[RuleCoverageItem] = []
    for spec in specs:
        profile_relevant = spec.rule_id in profile_union
        in_profile = (spec.rule_id in taiwan_keys) if profile_relevant else True
        if profile_relevant:
            in_engine = spec.rule_id in engine_keys
        else:
            in_engine = detect_flow_rule(spec.rule_id, gameplay_map)

        in_tests = detect_tests(spec.rule_id, test_map)
        gap_level = gap_level_for(
            spec_required=spec.required_in_taiwan_base,
            profile_relevant=profile_relevant,
            in_profile=in_profile,
            in_engine=in_engine,
            in_tests=in_tests,
        )

        layer_notes = [
            f"L1={'OK' if in_profile else 'MISS'}",
            f"L2={'OK' if in_engine else 'MISS'}",
            f"L4={'OK' if in_tests else 'MISS'}",
            f"catalog_status={spec.status}",
        ]
        if spec.excludes:
            layer_notes.append(f"excludes={';'.join(spec.excludes)}")
        if spec.includes:
            layer_notes.append(f"includes={';'.join(spec.includes)}")

        items.append(
            RuleCoverageItem(
                rule_id=spec.rule_id,
                zh_name=spec.zh_name,
                spec_required=spec.required_in_taiwan_base,
                in_profile=in_profile,
                in_engine=in_engine,
                in_tests=in_tests,
                gap_level=gap_level,
                notes=", ".join(layer_notes),
            )
        )

    required_total = sum(1 for spec in specs if spec.required_in_taiwan_base)
    covered_required = sum(
        1
        for item in items
        if item.spec_required and item.in_profile and item.in_engine
    )
    gaps = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for item in items:
        if item.gap_level in gaps:
            gaps[item.gap_level] += 1

    summary = CoverageSummary(
        total_rules=len(items),
        required_rules=required_total,
        covered_required_rules=covered_required,
        gaps_by_level=gaps,
    )
    return items, summary


def to_markdown(items: list[RuleCoverageItem], summary: CoverageSummary, taiwan_profile: str) -> str:
    return to_markdown_with_options(
        items=items,
        summary=summary,
        taiwan_profile=taiwan_profile,
        include_timestamp=False,
    )


def to_markdown_with_options(
    items: list[RuleCoverageItem],
    summary: CoverageSummary,
    taiwan_profile: str,
    include_timestamp: bool,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ") if include_timestamp else None
    lines: list[str] = []
    lines.append("# Rule Coverage Report")
    lines.append("")
    if now:
        lines.append(f"- Generated (UTC): `{now}`")
    lines.append(f"- Baseline profile: `{taiwan_profile}`")
    lines.append(f"- Total rules: `{summary.total_rules}`")
    lines.append(
        f"- Required coverage: `{summary.covered_required_rules}/{summary.required_rules}`"
    )
    lines.append(
        "- Gap counts: "
        + ", ".join(f"`{level}={count}`" for level, count in summary.gaps_by_level.items())
    )
    lines.append("")

    for level in ("P0", "P1", "P2", "P3"):
        level_rows = [item for item in items if item.gap_level == level]
        lines.append(f"## {level} Findings")
        if not level_rows:
            lines.append("- None")
        else:
            for item in level_rows:
                lines.append(
                    f"- `{item.rule_id}` ({item.zh_name}): profile={item.in_profile}, engine={item.in_engine}, tests={item.in_tests}"
                )
        lines.append("")

    lines.append("## Coverage Matrix")
    lines.append("")
    lines.append("| rule_id | zh_name | required | in_profile | in_engine | in_tests | gap_level |")
    lines.append("|---|---|:---:|:---:|:---:|:---:|:---:|")
    for item in items:
        lines.append(
            f"| `{item.rule_id}` | {item.zh_name} | {'Y' if item.spec_required else 'N'} | {'Y' if item.in_profile else 'N'} | {'Y' if item.in_engine else 'N'} | {'Y' if item.in_tests else 'N'} | {item.gap_level or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _validate_inputs(
    catalog_path: Path,
    profiles_dir: Path,
    scoring_rules_dir: Path,
    gameplay_dir: Path,
    tests_dir: Path,
    taiwan_profile: str,
) -> None:
    if not catalog_path.exists():
        raise FileNotFoundError(f"Rule catalog not found: {catalog_path}")
    if not catalog_path.is_file():
        raise ValueError(f"Rule catalog must be a file: {catalog_path}")
    if not profiles_dir.exists() or not profiles_dir.is_dir():
        raise FileNotFoundError(f"Profiles directory not found: {profiles_dir}")
    if not any(profiles_dir.glob("*.json")):
        raise ValueError(f"No profile JSON files found in: {profiles_dir}")
    if not scoring_rules_dir.exists() or not scoring_rules_dir.is_dir():
        raise FileNotFoundError(f"Scoring rules directory not found: {scoring_rules_dir}")
    if not any(scoring_rules_dir.glob("*.py")):
        raise ValueError(f"No scoring rule .py files found in: {scoring_rules_dir}")
    if not gameplay_dir.exists() or not gameplay_dir.is_dir():
        raise FileNotFoundError(f"Gameplay directory not found: {gameplay_dir}")
    if not tests_dir.exists() or not tests_dir.is_dir():
        raise FileNotFoundError(f"Tests directory not found: {tests_dir}")
    if not str(taiwan_profile or "").strip():
        raise ValueError("taiwan_profile must be a non-empty string")


def run_audit(
    catalog_path: Path,
    profiles_dir: Path,
    scoring_rules_dir: Path,
    gameplay_dir: Path,
    tests_dir: Path,
    output_json: Path,
    output_md: Path,
    taiwan_profile: str,
    include_timestamp: bool = False,
) -> tuple[list[RuleCoverageItem], CoverageSummary]:
    _validate_inputs(
        catalog_path=catalog_path,
        profiles_dir=profiles_dir,
        scoring_rules_dir=scoring_rules_dir,
        gameplay_dir=gameplay_dir,
        tests_dir=tests_dir,
        taiwan_profile=taiwan_profile,
    )
    specs = load_rule_catalog(catalog_path)
    profiles = load_profiles(profiles_dir)
    if taiwan_profile not in profiles:
        available = ", ".join(sorted(profiles.keys()))
        raise ValueError(
            f"Profile '{taiwan_profile}' not found in {profiles_dir}. Available: {available}"
        )
    engine_keys = scan_engine_keys(scoring_rules_dir)

    gameplay_files = list(gameplay_dir.glob("*.py"))
    gameplay_map = read_text_map(gameplay_files)
    test_map = read_text_map(tests_dir.rglob("test_*.py"))

    items, summary = build_coverage(
        specs=specs,
        profiles=profiles,
        taiwan_profile=taiwan_profile,
        engine_keys=engine_keys,
        gameplay_map=gameplay_map,
        test_map=test_map,
    )

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    json_payload = {
        "summary": asdict(summary),
        "items": [asdict(item) for item in items],
    }
    output_json.write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    output_md.write_text(
        to_markdown_with_options(items, summary, taiwan_profile, include_timestamp),
        encoding="utf-8",
    )
    return items, summary


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Audit Taiwan16 rule coverage")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=root / "docs" / "audit" / "rule_catalog.csv",
        help="Rule catalog CSV path",
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=root / "configs" / "scoring" / "profiles",
        help="Scoring profiles directory",
    )
    parser.add_argument(
        "--scoring-rules-dir",
        type=Path,
        default=root / "domain" / "scoring" / "rules",
        help="Scoring rule implementation directory",
    )
    parser.add_argument(
        "--gameplay-dir",
        type=Path,
        default=root / "domain" / "gameplay",
        help="Gameplay rule implementation directory",
    )
    parser.add_argument(
        "--tests-dir",
        type=Path,
        default=root / "tests",
        help="Tests directory",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=root / "reports" / "rule_coverage.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=root / "reports" / "rule_coverage.md",
        help="Output Markdown path",
    )
    parser.add_argument(
        "--taiwan-profile",
        default="taiwan_base",
        help="Baseline profile key",
    )
    parser.add_argument(
        "--include-timestamp",
        action="store_true",
        help="Include generation timestamp in markdown report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _, summary = run_audit(
        catalog_path=args.catalog,
        profiles_dir=args.profiles_dir,
        scoring_rules_dir=args.scoring_rules_dir,
        gameplay_dir=args.gameplay_dir,
        tests_dir=args.tests_dir,
        output_json=args.output_json,
        output_md=args.output_md,
        taiwan_profile=args.taiwan_profile,
        include_timestamp=args.include_timestamp,
    )

    print(
        "Rule audit completed: "
        f"required_covered={summary.covered_required_rules}/{summary.required_rules}, "
        f"gaps={summary.gaps_by_level}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
