from __future__ import annotations
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Tuple

from .types import ScoringTable


@lru_cache(maxsize=16)
def load_scoring_assets(profile_name: str, override_path: str | None = None) -> ScoringTable:
    """
    Load scoring table and labels for a given profile.
    Search order:
      1) `override_path` or env MAHJONG16_SCORING_JSON (if provided)
      2) project root `taiwanese_mahjong_scoring.json`

    Supports two JSON shapes:
      - { "<profile_name>": { ... }, "labels": { ... } }
      - { "profiles": { "<profile_name>": { ... } }, "labels": { ... } }
    """
    candidates: list[Path] = []
    path_str = override_path or os.environ.get("MAHJONG16_SCORING_JSON")
    if path_str:
        candidates.append(Path(path_str))

    try:
        proj_root = Path(__file__).resolve().parent.parent.parent
        default_json = proj_root / "taiwanese_mahjong_scoring.json"
        candidates.append(default_json)
    except Exception:
        pass

    for p in candidates:
        try:
            if p.is_file():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                table = None
                labels = None
                if isinstance(data, dict):
                    if "profiles" in data and isinstance(data["profiles"], dict):
                        table = data["profiles"].get(profile_name)
                    if table is None and profile_name in data and isinstance(data[profile_name], dict):
                        table = data[profile_name]
                    if isinstance(data.get("labels"), dict):
                        labels = data["labels"]
                if isinstance(table, dict):
                    return ScoringTable(values=table, labels=(labels or {}))
        except Exception:
            continue

    raise FileNotFoundError(
        f"Scoring JSON not found or profile '{profile_name}' missing. "
        f"Provide taiwanese_mahjong_scoring.json or set MAHJONG16_SCORING_JSON."
    )

