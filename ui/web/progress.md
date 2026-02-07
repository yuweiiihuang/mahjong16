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
- Added anchor fixture wiring for `anchor-01-self-draw`: only one draw seat is rendered at a time.
- Updated e2e output naming to anchor-based artifacts (`anchor-01-self-draw.png/.json`).

### Validation

- `npm run lint`: pass (with a non-blocking `baseline-browser-mapping` staleness warning).
- `npm run test`: pass (1/1 tests).
- `npm run build`: pass.
- `npm run test:e2e:ui`: expected fail, blocked by missing local `playwright` package.

### TODO

- Install `playwright` in `ui/web` when network access is available.
- Expand action payloads into scenario-specific sequences once the UI has interactive controls.
- Add a visual baseline approval step (diff review) when layouts start changing frequently.

- 2026-02-07: 將下家棄牌區/花牌區下移到與上家點對稱位置（right-discard 4/8、right-flower 8/10），使花牌區緊貼我方進牌區上方且不重疊。

- 2026-02-07: 將我方花牌/棄牌區整組右移（self-flower 4/6、self-discard 6/10），右側貼齊下家花牌左緣。

- 2026-02-07: 上家棄牌區往下擴增一個 row（left-discard 4/9），並將上家棄牌示例擴至 21 張（3x7）。

- 2026-02-07: 下家棄牌區往上擴增一個 row（right-discard 3/8），並將下家棄牌改為 21 張；右側棄牌網格 rows 改為 7（3x7）。

- 2026-02-07: 我方與對家棄牌改為 21 張，並將中路棄牌網格欄數調整為 7（3x7），檢查編號順序連續。

- 2026-02-07: 修正我方棄牌區垂直置中：self-discard region-content 改為 justify-content:center，並移除 discard-grid-self 的 margin-top。

- 2026-02-07: 修正對家棄牌區垂直置中：opp-discard region-content 改為 justify-content:center，並移除 discard-grid-opp 的 margin-top。
