# Repository Guidelines

## Project Structure & Module Organization
`core/` hosts the Mahjong16 rules engine and scoring (`core/env.py`, `core/scoring/engine.py`); keep logic pure, deterministic, and free of side effects. `app/` contains CLI demos and strategy wiring, while `ui/console.py` handles rendering helpers shared across clients. Place bots in `bots/` and reinforcement-learning scaffolding in `rl/`; both should import from `core/` or `ui/` instead of copying utilities. Treat `scripts/` (e.g., `scripts/eval_league.py`, `scripts/bench_sim.py`) and the JSON assets under `configs/` as read-only inputs, and mirror new code with matching suites in `tests/` (see `tests/test_env_basic.py`).

## Build, Test, and Development Commands
- `pip install -r requirements.txt` — install runtime dependencies plus pytest.
- `python main.py` — launch the interactive CLI table for manual smoke checks.
- `python -m core.env` — run the environment module directly for import-safe experiments.
- `pytest -q` — execute the regression suite; ensure it passes before every PR.
- `python scripts/bench_sim.py -n 10000` — benchmark the environment; use when tuning performance-sensitive changes.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation and lines ≤ 100 characters to stay consistent with existing modules. Use snake_case for functions and variables, PascalCase for classes, and upper snake case for constants such as `PRIORITY`. Annotate public APIs with type hints and docstrings that explain rule decisions. Prefer composition over globals by passing `Ruleset` instances or explicit context objects.

## Testing Guidelines
Write pytest suites named `test_*.py`, colocated with the modules they verify. Cover both success and failure paths, including dead-wall handling and reaction priority. Parameterize scenarios across seat winds or rule toggles, and seed RNGs via `Mahjong16Env(seed=...)` or `Ruleset.random_seed` to keep runs reproducible. Add regression cases whenever scoring tables or rules change.

## Commit & Pull Request Guidelines
Use Conventional Commits with English types (`feat`, `fix`, `chore`) and concise summaries, e.g., `feat: add four-concealed-meld fan`. Scope commits narrowly and mention follow-up commands or data migrations when behavior shifts. Pull requests should summarize intent, list touched modules (e.g., `core/env.py`, `ui/console.py`), link issues, and attach CLI screenshots or pytest output for changes affecting scoring or UX.

## Configuration & Safety Notes
Extend `core/ruleset.py` for new table options rather than scattering rule toggles. Preserve keys consumed by `core/scoring/tables.py` when editing `configs/` assets—treat those JSON files as read-only history. Provide deterministic seeds when introducing bots or training loops, and avoid writing to shared state outside the workspace.
