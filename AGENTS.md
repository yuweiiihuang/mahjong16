# Repository Guidelines

## Project Structure & Module Organization
- Core rules and scoring live in `core/` (see `core/env.py`, `core/scoring/engine.py`); keep them pure and deterministic.
- CLI demos and strategies sit in `app/`, with rendering helpers in `ui/console.py` and shared formatting utilities.
- Bots (`bots/`) and RL scaffolding (`rl/`) stay decoupled from the core; import shared helpers instead of duplicating logic.
- Data assets (`taiwanese_mahjong_scoring.json`) and scripts (`scripts/eval_league.py`, `scripts/bench_sim.py`) should remain read-only inputs.
- Tests in `tests/` mirror module names (`test_env_basic.py`, `test_scoring.py`); keep fixtures beside the suites they serve.

## Build, Test, and Development Commands
```bash
pip install -r requirements.txt   # install runtime deps + pytest
python main.py                    # run the interactive CLI demo
pytest -q                         # execute the regression suite
python scripts/bench_sim.py -n 10000  # optional environment benchmark
```
Keep experiments import-safe by launching modules with `python -m` (e.g., `python -m core.env`).

## Coding Style & Naming Conventions
- Adopt PEP 8 with 4-space indents and lines ≤ 100 chars to align with current modules.
- Use snake_case for functions/variables, PascalCase for classes, and UPPER_SNAKE for constants like `PRIORITY`.
- Annotate public APIs with type hints and docstrings that clarify rule decisions; leave helpers in `core/hand.py` and `core/tiles.py` pure for deterministic testing.
- Favor composition over globals: pass `Ruleset` instances or context objects instead of setting module-level defaults.

## Testing Guidelines
- Tests run on `pytest`; name files `test_*.py` and mirror new modules (`tests/test_reaction_basic.py`).
- Cover both success and failure paths (dead-wall handling, reaction priority) and seed RNGs when randomness is involved.
- Use parametrization for seat winds or rule toggles to catch regressions quickly.
- Run `pytest -q` before each PR and add regression cases whenever scoring tables or rules change.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat: 新增計算支付功能...`, `chore: ui新增多局贏家摘要功能`); keep the type in English and the summary concise.
- Scope commits narrowly and include context or example commands when behavior shifts.
- PRs should outline intent, list touched modules (e.g., `core/env.py`, `ui/console.py`), link issues, and attach CLI screenshots or test output for UI or scoring changes.

## Configuration & Safety Notes
- Extend `core/ruleset.py` for new table options instead of inlining rule tweaks in callers.
- Preserve keys consumed by `core/scoring/tables.py` when editing `taiwanese_mahjong_scoring.json`.
- Provide deterministic seeds via `Mahjong16Env(seed=...)` or `Ruleset.random_seed` when adding bots or training loops.
