from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module(repo_root: Path):
    script_path = repo_root / "scripts" / "audit_rule_coverage.py"
    spec = importlib.util.spec_from_file_location("audit_rule_coverage", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_audit_writes_outputs_and_flags_missing_required(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    mod = _load_module(repo_root)

    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "\n".join(
            [
                "rule_id,zh_name,source_doc,required_in_taiwan_base,tai_value,trigger,"
                "excludes,includes,status",
                "alpha,Alpha,doc,true,1,t,,,implemented",
                "flow_required,Flow Required,doc,true,0,t,,,missing",
                "flow_optional,Flow Optional,doc,false,0,t,,,missing",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "taiwan_base.json").write_text('{"alpha": 1}\n', encoding="utf-8")

    scoring_rules_dir = tmp_path / "scoring_rules"
    scoring_rules_dir.mkdir()
    (scoring_rules_dir / "r.py").write_text('acc.add("alpha")\n', encoding="utf-8")

    gameplay_dir = tmp_path / "gameplay"
    gameplay_dir.mkdir()
    (gameplay_dir / "g.py").write_text("pass\n", encoding="utf-8")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_alpha.py").write_text('assert "alpha"\n', encoding="utf-8")

    output_json = tmp_path / "out" / "rule_coverage.json"
    output_md = tmp_path / "out" / "rule_coverage.md"

    items, summary = mod.run_audit(
        catalog_path=catalog,
        profiles_dir=profiles_dir,
        scoring_rules_dir=scoring_rules_dir,
        gameplay_dir=gameplay_dir,
        tests_dir=tests_dir,
        output_json=output_json,
        output_md=output_md,
        taiwan_profile="taiwan_base",
    )

    assert output_json.exists()
    assert output_md.exists()

    by_id = {item.rule_id: item for item in items}
    assert by_id["alpha"].gap_level == ""
    assert by_id["flow_required"].gap_level == "P0"
    assert by_id["flow_optional"].gap_level == "P2"

    assert summary.required_rules == 2
    assert summary.covered_required_rules == 1
    assert summary.gaps_by_level["P0"] == 1

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["summary"]["total_rules"] == 3


def test_scan_engine_keys_extracts_acc_add_calls(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    mod = _load_module(repo_root)

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "one.py").write_text('acc.add("k1")\nacc.add("k2", count=2)\n', encoding="utf-8")
    (rules_dir / "two.py").write_text('print("no-op")\n', encoding="utf-8")

    keys = mod.scan_engine_keys(rules_dir)
    assert keys == {"k1", "k2"}
