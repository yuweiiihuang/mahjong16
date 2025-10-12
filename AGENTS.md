# Repository Guidelines

## Project Structure & Module Organization
- Place core rules and scoring logic in `core/`; keep modules pure and deterministic (`core/env.py`, `core/scoring/engine.py`).
- Wire strategies and CLI demos through `app/`, and reuse console helpers from `ui/console.py` instead of duplicating render logic.
- Host autonomous players in `bots/` and reinforcement-learning tools in `rl/`, importing shared utilities from `core/` or `ui/`.
- Treat `scripts/` (e.g., `scripts/bench_sim.py`) and config assets under `configs/` as read-only inputs; mirror any new runtime behavior with tests in `tests/`.

## Build, Test, and Development Commands
- Always activate the project venv before running commands: `source .venv/bin/activate`.
- `pip install -r requirements.txt` installs runtime dependencies and pytest extras.
- `python main.py` launches the interactive CLI table for manual rule smoke-checks.
- `python -m domain.gameplay.env` runs the environment module directly to validate import safety (legacy `python -m core.env` remains as a shim).
- `pytest -q` executes the regression suite; confirm a clean run before publishing changes.
- `python scripts/bench_sim.py -n 10000` benchmarks the engine; use when tuning performance-sensitive code.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and keep lines ≤ 100 characters.
- Use snake_case for variables/functions, PascalCase for classes, and UPPER_SNAKE for constants like `PRIORITY`.
- Annotate public APIs with type hints and docstrings that clarify rule decisions; prefer composition over globals by passing `Ruleset` instances or explicit context objects.

## Testing Guidelines
- Add pytest suites named `test_*.py` alongside the modules they cover (see `tests/test_env_basic.py`).
- Cover success and failure paths, including dead-wall and reaction priority scenarios; seed runs via `Mahjong16Env(seed=...)` or `Ruleset.random_seed` for determinism.
- Update or extend regression cases whenever scoring tables or rule toggles change.

## Commit & Pull Request Guidelines
- Use Conventional Commits (e.g., `feat: add four-concealed-meld fan`) with concise English summaries.
- Scope commits narrowly; mention any follow-up commands or data migrations when behavior shifts.
- Pull requests should summarize intent, list touched modules (e.g., `core/env.py`, `ui/console.py`), link relevant issues, and attach CLI screenshots or pytest output for UX or scoring changes.

## Configuration & Safety Notes
- Extend `core/ruleset.py` for new table options rather than scattering toggles.
- Preserve keys consumed by `core/scoring/tables.py` when reading from `configs/`; never overwrite historical assets.
- Provide deterministic seeds when introducing bots or training loops, and avoid writing to shared state outside the workspace.
