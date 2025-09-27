# Repository Guidelines

## Project Structure & Module Organization
`core/` hosts the tile model, rules engine, and scoring pipeline—extend rules in `core/ruleset.py` and keep hand logic pure inside `core/hand.py`. Runtime helpers live in `app/` (CLI strategies and formatting), while reusable console views sit in `ui/console.py`. Sample opponents are under `bots/`, and reinforcement-learning scaffolding (`rl/`) bundles the policy/value net, replay buffer, and self-play loop. Utility scripts for evaluation reside in `scripts/`, shared scoring tables in `taiwanese_mahjong_scoring.json`, and regression tests in `tests/`.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` – create an isolated Python 3.13 environment.
- `pip install -r requirements.txt` – install runtime and testing dependencies.
- `python main.py` – launch the CLI demo using Rich output.
- `pytest -q` – run the entire regression suite.
- `pytest tests/test_scoring.py -k fan` – execute focused scoring scenarios when iterating on point tables.

## Coding Style & Naming Conventions
Adopt four-space indentation, type hints, and module-level docstrings for new public APIs. Follow `snake_case` for functions and variables (`legal_actions`), `PascalCase` for classes (`Mahjong16Env`), and `UPPER_CASE` for constants (`PRIORITY`). Keep environment stateful code under `core/env.py` and leave mathematical helpers pure for easier testing. When modifying console output, favor Rich constructs already used in `ui/console.py`.

## Testing Guidelines
Author tests alongside features in the matching `tests/test_*.py` module—mirror existing names like `test_tsumo.py`. Use descriptive function names (`test_deadwall_reserves_tail`) and arrange Act/Assert clearly. Every new rule path should have at least one regression test covering the happy path and a guard against illegal actions. Run `pytest -q` locally before submitting, plus any targeted module tests relevant to your change.

## Commit & Pull Request Guidelines
Follow the observed Conventional Commit style: `<type>: short summary` (e.g., `feat: 新增計算支付功能及相關UI更新`). Keep the subject imperative and under ~72 characters; optional body lines explain context or follow-ups. Pull requests should link issues when available, outline validation commands (pytest or manual steps), and include screenshots for UI changes in `app/` or `ui/`. Mention updates to scoring tables or rules so reviewers can double-check downstream effects.

## Configuration & Data Tips
Scoring behaviour is driven by `taiwanese_mahjong_scoring.json`; when altering fan values, document the changes and add regression tests under `tests/test_scoring.py`. Custom rulesets belong in subclasses or presets of `core/ruleset.py`, keeping defaults backward compatible. Large assets or notebooks should land outside the core tree and be referenced, not committed, unless they are required fixtures.
