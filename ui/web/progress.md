Original prompt: 你可以建議一個開發流程嗎？我現在就是做一個改動就動一個，然後再截圖確認，有沒有更高效的方法

## 2026-02-06

- Added `npm run test:e2e:ui` to run a repeatable UI screenshot flow via the skill Playwright client.
- Added `npm run test:gate` as a pre-merge gate (`lint + unit + build + e2e`).
- Added `scripts/run-ui-e2e.mjs` to standardize URL, actions, and output folder.
- Added `e2e/actions/layout-smoke.json` as the default action payload.
- Added `window.render_game_to_text` in `src/components/Table.tsx` so state snapshots are exported on each run.
- Network in this environment cannot reach npm registry, so `playwright` package install is currently blocked.
- Updated `vite.config.ts` to use `defineConfig` from `vitest/config` so the `test` block type-checks in build.
- Updated `tsconfig.app.json` / `tsconfig.test.json` to keep app builds from type-checking test globals.
- Replaced the initial skill-client wrapper with a local Playwright runner because Chromium launch flags in the skill client aborted in this environment.

### Validation

- `npm run lint`: pass (with a non-blocking `baseline-browser-mapping` staleness warning).
- `npm run test`: pass (1/1 tests).
- `npm run build`: pass.
- `npm run test:e2e:ui`: expected fail, blocked by missing local `playwright` package.

### TODO

- Install `playwright` in `ui/web` when network access is available.
- Expand action payloads into scenario-specific sequences once the UI has interactive controls.
- Add a visual baseline approval step (diff review) when layouts start changing frequently.
