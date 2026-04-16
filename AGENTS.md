# Repository Guidelines

## Project Structure & Module Organization
- Keep deterministic rules, scoring, and utilities under `domain/` (e.g., `domain/gameplay/game_env.py`, `domain/scoring/engine.py`).
- Route CLI flows and demos through `app/`, reusing `ui/console.py` for rendering instead of duplicating output helpers.
- Place autonomous agents in `bots/` and any reinforcement-learning tooling in `rl/`, importing shared logic from `domain/` or `ui/` as needed.
- Treat `configs/` and `scripts/` as read-only inputs; introduce new runtime behaviour alongside pytest coverage in `tests/`.

## Build, Test, and Development Commands
- `source .venv/bin/activate` — activate the project environment before installing or running tools.
- `pip install -r requirements.txt` — sync runtime and test dependencies.
- `python main.py` — launch the interactive table view for smoke-checking rules.
- `python -m domain.gameplay.game_env` — validate module imports without invoking the CLI.
- `pytest -q` — execute the regression suite; ensure a clean run before publishing.
- `python scripts/bench_sim.py -n 10000` — benchmark engine performance when tuning heuristics.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and keep lines at or below 100 characters.
- Use snake_case for functions and variables, PascalCase for classes, and UPPER_SNAKE for constants like `PRIORITY`.
- Annotate public APIs with type hints and docstrings that clarify rule decisions; prefer composition over globals by passing explicit context objects.

## Testing Guidelines
- Add `test_*.py` modules next to the code under test, mirroring new gameplay or scoring scenarios.
- Use pytest fixtures and deterministic seeds (`Mahjong16Env(seed=...)`, `Ruleset.random_seed`) to cover success, failure, and dead-wall edge cases.
- Update regression cases whenever scoring tables or rule toggles change.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat: add four-concealed-meld fan`, `fix: adjust ron priority ordering`).
- Scope commits narrowly and call out follow-up commands or data migrations if behaviour shifts.
- Summarise PR intent, list touched modules (e.g., `domain/gameplay/game_env.py`, `ui/console.py`), link issues, and attach CLI screenshots or `pytest` output for UX or scoring updates.

## Security & Configuration Tips
- Extend `domain/rules/ruleset.py` for new table options; avoid scattering toggles.
- Do not overwrite historical assets under `configs/`; preserve keys consumed by `domain/scoring/lookup.py`.
- Seed bots and training loops deterministically and avoid writing outside the workspace.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
