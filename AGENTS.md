# Repository Guidelines

## Project Structure & Module Organization
- Keep deterministic rules, scoring, and utilities under `domain/` (e.g., `domain/gameplay/game_env.py`, `domain/scoring/engine.py`).
- Route CLI flows and demos through `app/`, reusing `ui/console.py` for rendering instead of duplicating output helpers.
- Place autonomous agents in `bots/` and any reinforcement-learning tooling in `rl/`, importing shared logic from `domain/` or `ui/` as needed.
- Treat `configs/` as read-only input data; keep new runtime behaviour in `domain/`, `app/`, `bots/`,
  or `rl/`, then cover it with pytest in `tests/`.
- Keep operational tooling in `scripts/` (`bench_sim`, `eval_league`, analytics, tuning) and document
  new script flags in `scripts/README.md` when behaviour changes.

## Build, Test, and Development Commands
- `source .venv/bin/activate` — activate the project environment before installing or running tools.
- `pip install -r requirements.txt` — sync runtime and test dependencies.
- `python main.py --help` — inspect CLI options and validate argument wiring.
- `python main.py` — launch the interactive table view for smoke-checking rules.
- `python main.py --seed 42 --human 0 --bot greedy --hands 8` — run a deterministic interactive smoke test.
- `python main.py --no-ui --hands 50 --log-dir logs/demo` — run headless and emit per-hand CSV summaries.
- `python main.py --sessions 8 --cores 4 --hands 32 --bot auto` — run batch headless sessions in parallel.
- `python main.py --jangs 1 --no-ui` — run full-jang flow validation (cannot be combined with finite `--hands`).
- `python -m domain.gameplay.game_env` — validate module imports without invoking the CLI.
- `pytest -q` — execute the regression suite; ensure a clean run before publishing.
- `pytest -q tests/env tests/scoring` — focused regression run for gameplay/scoring changes.
- `python scripts/bench_sim.py -n 10000 --bot auto` — benchmark simulation throughput.
- `python scripts/eval_league.py --hands 32 --matches 2 --seed 2024 auto greedy random rulebot` — compare bot pools.
- `python scripts/analyze_breakdown_flags.py` — inspect latest log CSV breakdown frequencies.
- `python scripts/tune_greedy_weights.py --hands 512 --trials 30 --seed 42` — tune greedy heuristics locally.
- `cd ui/web && npm install` — install web UI dependencies.
- `cd ui/web && npm run dev` — run Vite UI locally.
- `cd ui/web && npm run test` — run Vitest component tests.
- `cd ui/web && npm run lint` — lint UI code.
- `cd ui/web && npm run build` — create production UI bundle.

## Development Workflows
- **Interactive rule smoke test**: run `python main.py --seed <seed> --human <seat> --bot greedy --hands <n>`
  to verify turn order, reaction prompts, and console rendering.
- **Headless/batch simulation**: use `--no-ui` for single-session CSV logging, or `--sessions` + `--cores`
  for multi-process throughput runs; omit `--log-dir` only when transient logs are acceptable.
- **League evaluation loop**: use `scripts/eval_league.py` with fixed `--seed` and `--matches` to compare bots;
  persist machine-readable summaries with `--json-out`.
- **Scoring analytics loop**: generate logs via headless runs, then call
  `scripts/analyze_breakdown_flags.py [csv] --profile <name>` to inspect breakdown-tag frequency shifts.
- **Greedy tuning loop**: run `scripts/tune_greedy_weights.py` with deterministic seeds, then re-check outcomes
  using `scripts/bench_sim.py` and targeted pytest modules.
- **Web UI loop**: develop in `ui/web` with `npm run dev`, gate with `npm run test` and `npm run lint`, and
  verify release readiness with `npm run build`.

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
