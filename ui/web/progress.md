## 修正方向紀錄

- 2026-02-06:
  - 新增 `npm run test:e2e:ui`，建立可重現的 UI 截圖流程。
  - 新增 `npm run test:gate`，作為 pre-merge gate（`lint + unit + build + e2e`）。
  - 新增 `scripts/run-ui-e2e.mjs`，統一 URL、actions 與輸出資料夾。
  - 新增 `e2e/actions/layout-smoke.json`，作為預設 action payload。
  - 在 `Table.tsx` 新增 `window.render_game_to_text`，每次執行輸出 state snapshot。
  - e2e 產物改為 anchor 命名（`anchor-01-self-draw.png/.json`）。
  - `vite.config.ts` 改用 `vitest/config` 的 `defineConfig`，讓 `test` 區塊可正確 type-check。
  - 更新 `tsconfig.app.json` / `tsconfig.test.json`，避免 app build 混入 test globals。
  - 原 skill-client wrapper 改為本地 Playwright runner，避免 Chromium flag 問題。

- 2026-02-07:
  - 將下家棄牌區/花牌區下移到與上家點對稱位置（right-discard 4/8、right-flower 8/10），使花牌區緊貼我方進牌區上方且不重疊。
  - 將我方花牌/棄牌區整組右移（self-flower 4/6、self-discard 6/10），右側貼齊下家花牌左緣。
  - 上家棄牌區往下擴增一個 row（left-discard 4/9），並將上家棄牌示例擴至 21 張（3x7）。
  - 下家棄牌區往上擴增一個 row（right-discard 3/8），並將下家棄牌改為 21 張；右側棄牌網格 rows 改為 7（3x7）。
  - 我方與對家棄牌改為 21 張，並將中路棄牌網格欄數調整為 7（3x7），檢查編號順序連續。
  - 修正我方棄牌區垂直置中：self-discard region-content 改為 justify-content:center，並移除 discard-grid-self 的 margin-top。
  - 修正對家棄牌區垂直置中：opp-discard region-content 改為 justify-content:center，並移除 discard-grid-opp 的 margin-top。
  - 四家花牌區新增實際牌面渲染（各 8 張），新增 TableState flower 欄位與 flower-grid/flower-tile 樣式。
  - 花牌顯示改為順序 1~8；修正上家/下家花牌排列方向（上家按欄由上到下，下家鏡像）。
  - 修正上家/下家花牌順序檢查模式：改為畫面同向遞增（1 2 / 3 4 / 5 6 / 7 8）。
  - 移除左右花牌縮小樣式，左右花牌改為與上下同規格 4x2 顯示，避免過小並讓順序直觀。
  - 上家花牌整組向右旋轉 90 度，並將上家花牌區下擴一個 grid row；上家棄牌區下移一個 row，避免重疊。
  - 上家花牌改為左上角對齊，並調整旋轉後可視順序為左上到右下遞增。
  - 上家花牌改為左上對齊 2x4 直式格，移除 transform 偏移，順序改為左上到右下。
  - 修正上家花牌方向：left-flower 的 flower-tile 旋轉 90 度。
  - 上家花牌方向改為側邊牌樣式（tile 尺寸轉橫向 + 字旋轉90），移除直接旋轉 tile 造成的錯位。
  - 上家花牌改為欄優先順序（左上->左下->右上->右下），left-flower flower-grid 加上 grid-auto-flow: column。
  - 下家花牌改為側邊方向與欄優先順序（vertical + grid-auto-flow: column，牌面旋轉 -90）。
  - 下家花牌區上擴一個 row（7/10），下家棄牌區上移（2/7）；下家花牌順序改為右下->右上->左下->左上（顯式 gridRow/gridColumn）。
  - 下家花牌改為貼齊花牌區右下角（right-flower flower-grid align-content:end，region-content justify-content:flex-end）。
  - Anchor fixture 調整為壓版面配置：棄牌上限 21，並將手牌/副露改為共用 16（示例為 10 手牌 + 2 副露）。
  - 修正上家副露渲染：改為「組別往下增長」，每組維持 3 張，並與手牌共用同一 side-rail 高度配額。
  - 新增 `anchor-left-meld-0` ~ `anchor-left-meld-5` 六組 anchor，對應副露 0~5 組與手牌 16/13/10/7/4/1。
  - 新增上家副露微調參數 `--left-meld-scale`；最終採用 `0.85` 作為不裁切且視覺平衡值。
  - 調整上家副露排版：組內貼齊、組間微重疊（-4）、並收緊上家副露與手牌間距（side-hand top inset = -8）。
  - 以最新設定重刷 0~5 截圖，輸出至 `ui/web/artifacts/ui-e2e/meld-sweep/anchor-left-meld-*.png`。

## TODO

- Expand action payloads into scenario-specific sequences once the UI has interactive controls.
- Add a visual baseline approval step (diff review) when layouts start changing frequently.
