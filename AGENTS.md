# Repository Guidelines

## Scope & File Placement
- Keep rules, scoring, and deterministic utilities in `domain/`, CLI flows in `app/`, bots in `bots/`, and RL tooling in `rl/`. Reuse `ui/console.py` for CLI rendering.
- Scripts in `scripts/` may be maintained when required by the task. Preserve historical `configs/` assets and keys consumed by `domain/scoring/lookup.py`; put new table options in `domain/rules/ruleset.py`.
- Store execution reports, test audits, and temporary validation records in Git-ignored `logs/execution-reports/`; exclude them from commits and pushes. Reserve `docs/` for maintained documentation and keep generated files inside the workspace.

## Web UI Baseline
- Use the Qinghe desktop table in `ui/web/` as the canonical Web UI design.
- Run through `python -m app.web --port 8000` (`app/web.py`); extend this UI without introducing another UI or an `app/web/` package that shadows the entry point.
- For legacy UI recovery, read `docs/webui-archive.md`.
- For UI changes, let the user test locally and obtain explicit approval before pushing; reuse approval already given for the same changes.

## Environment & Validation
- Use the locked `.venv` for project tools; run `uv sync --locked` when creating it or when dependency inputs change. `pip install -r requirements.txt` installs only the minimal CLI/Web and pytest dependencies.
- For a human CLI smoke check, run `python main.py --human 0 --hands 1`. Read `scripts/README.md` for simulation and analysis tool purposes; use each command's `--help` for current options.
- During development, run tests for the changed behavior and shared callers. Before publishing code, test, or runtime-configuration changes, run `pytest -q`; for frontend changes, also run `node --test tests/web/*.mjs`. Reuse passing results while the tested files, dependencies, and scope remain unchanged.
- For UI layout or interaction changes, check the affected desktop and mobile layouts in a browser. Read `tests/web/README.md` for browser checks; the Node suite does not execute the drag helper or prove WebGL/touch behavior.
- For new, modified, or audited tests, use `.agents/skills/mahjong-test-audit/SKILL.md`.

## Code & Tests
- Follow PEP 8, 4-space indentation, and a 100-character line limit. Give public APIs type hints and docstrings explaining rule decisions; pass explicit context instead of relying on globals.
- Place Python tests in the corresponding `tests/` subdirectory and Web JavaScript tests in `tests/web/`. Cover new runtime behavior and changes to scoring tables or rule toggles with regression cases.
- Use deterministic fixtures and seeds passed to `Mahjong16Env`, table managers, or bots; cover success, failure, and dead-wall cases where relevant.

## Task-Specific References
- For Docker deployment, backup, or rollback, read `docs/docker.md`; for gateway/authentication changes or cutover, also read `docs/gateway.md`.
- For room lifecycle or multiplayer changes, read `docs/multiplayer.md`; for recording, replay, or training exports, read `docs/hand-recording.md`.
- For iPhone safe-area or landscape layout changes, read `docs/iphone-table-safe-area.md`.

## Commits & Pull Requests
- Use narrowly scoped Conventional Commits. Describe the resulting behavior, validation, and any required commands or migrations in PRs; include screenshots for UI changes and test results for scoring changes.

## Agent skills

### Issue tracker
Track issues and specs in GitHub Issues. Read `docs/agents/issue-tracker.md`
before tracker operations.

### Triage labels
Use the five default triage roles. Read `docs/agents/triage-labels.md`
before classifying issues.

### Domain docs
Use a single root context. Read `docs/agents/domain.md` before domain exploration.
