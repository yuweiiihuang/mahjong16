from __future__ import annotations
import json
import os
from functools import lru_cache
from pathlib import Path

from .types import ScoringTable


@lru_cache(maxsize=16)
def load_scoring_assets(profile_name: str, override_path: str | None = None) -> ScoringTable:
    """Load a scoring profile and labels from JSON.

    Resolution order:
      1) ``override_path`` argument (or env var ``MAHJONG16_SCORING_JSON`` if set)
      2) Project root ``configs/scoring/profiles/<profile_name>.json`` (per-profile export)
      3) Project root ``configs/scoring/profiles/taiwan_base.json``
      4) Legacy fallback ``configs/profiles/<profile_name>.json`` then ``configs/<profile_name>.json``

    JSON shapes supported:
      - { "profiles": { "<profile>": {...} }, "labels": {...} }
      - { "<profile>": {...}, "labels": {...} }
      - { "<profile key>": <int>, ... }  # per-profile export

    Args:
      profile_name: Profile key to load (e.g., 'taiwan_base').
      override_path: Optional explicit JSON file path.

    Returns:
      ScoringTable with values and labels for the profile.

    Raises:
      FileNotFoundError: When no file found or profile missing.
    """
    candidates: list[Path] = []
    path_str = override_path or os.environ.get("MAHJONG16_SCORING_JSON")
    if path_str:
        candidates.append(Path(path_str))

    proj_root = _project_root()
    configs_dir = proj_root / "configs"
    scoring_dir = configs_dir / "scoring"
    profiles_dir = scoring_dir / "profiles"
    if not path_str:
        candidates.append(profiles_dir / f"{profile_name}.json")
        if profile_name != "taiwan_base":
            candidates.append(profiles_dir / "taiwan_base.json")
        # Backwards compatibility for repos still on configs/profiles/
        legacy_profiles_dir = configs_dir / "profiles"
        candidates.append(legacy_profiles_dir / f"{profile_name}.json")
        if profile_name != "taiwan_base":
            candidates.append(legacy_profiles_dir / "taiwan_base.json")
        # Legacy fallback for overrides that may still point to configs/<profile>.json
        candidates.append(configs_dir / f"{profile_name}.json")
        if profile_name != "taiwan_base":
            candidates.append(configs_dir / "taiwan_base.json")

    seen: set[Path] = set()
    for p in candidates:
        try:
            if not p or p in seen:
                continue
            seen.add(p)
            if p.is_file():
                with p.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                table, labels = _extract_table_and_labels(data, profile_name)
                if isinstance(table, dict):
                    resolved_labels = _resolve_labels(profile_name, table, labels)
                    return ScoringTable(values=table, labels=resolved_labels)
        except Exception:
            continue

    raise FileNotFoundError(
        f"Scoring JSON not found or profile '{profile_name}' missing. "
        f"Provide configs/profiles/taiwan_base.json or set MAHJONG16_SCORING_JSON."
    )


def _project_root() -> Path:
    try:
        return Path(__file__).resolve().parent.parent.parent
    except Exception:
        return Path.cwd()


def _extract_table_and_labels(data: object, profile_name: str):
    table = None
    labels = None
    if isinstance(data, dict):
        profiles = data.get("profiles")
        if isinstance(profiles, dict):
            candidate = profiles.get(profile_name)
            if isinstance(candidate, dict):
                table = candidate
        if table is None:
            direct = data.get(profile_name)
            if isinstance(direct, dict):
                table = direct
        if table is None and data and all(isinstance(v, (int, float)) for v in data.values()):
            table = data
        labels_candidate = data.get("labels")
        if isinstance(labels_candidate, dict):
            labels = labels_candidate
    return table, labels


def _resolve_labels(profile_name: str, table: dict[str, object], explicit_labels: dict[str, object] | None) -> dict[str, str]:
    resolved: dict[str, str]
    if explicit_labels:
        resolved = {str(k): str(v) for k, v in explicit_labels.items()}
    else:
        resolved = _load_default_labels()

    if not resolved:
        raise ValueError(
            f"Scoring labels missing for profile '{profile_name}'. "
            "Provide labels in the same JSON or update configs/labels.json."
        )

    missing = [key for key in table.keys() if not str(resolved.get(key, "")).strip()]
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(
            f"Scoring labels missing entries for profile '{profile_name}': {missing_str}. "
            "Update configs/labels.json or include labels alongside the profile."
        )

    return resolved


@lru_cache(maxsize=1)
def _load_default_labels() -> dict[str, str]:
    configs_dir = _project_root() / "configs"
    scoring_dir = configs_dir / "scoring"
    path = scoring_dir / "labels.json"
    if not path.is_file():
        legacy = configs_dir / "labels.json"
        if not legacy.is_file():
            return {}
        path = legacy
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}
    return {}
