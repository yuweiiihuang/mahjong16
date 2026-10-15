# scripts 使用指南

以下指令從專案根目錄執行。使用 `uv sync --locked` 後啟用 `.venv`；
最小依賴亦可使用 `pip install -r requirements.txt`。完整選項以各腳本的 `--help` 為準。

## analyze_breakdown_flags.py
- 用途：統計戰報（CSV）中的 breakdown 標籤出現頻率。
- 基本用法：
  - `python scripts/analyze_breakdown_flags.py [CSV檔路徑]`
  - 若未指定 CSV，腳本會搜尋 `logs/` 內最新的戰報檔案並使用。
- 常見選項：
  - `--scoring-json PATH`：指定另一個計分設定 JSON 以決定旗標順序。
  - `--profile PROFILE_NAME`：指定計分 profile（預設 `taiwan_base`）。
  - `--only FLAG FLAG...`：只輸出特定旗標；順序仍遵照 JSON 定義。
- 範例：
  - `python scripts/analyze_breakdown_flags.py logs/2024-05-18/table.csv --only self_pick discard_win`

## eval_league.py
- 用途：建立多組代理（bot）對戰的聯盟賽，並彙整積分統計。
- 基本用法：
  - `python scripts/eval_league.py [選項] AGENT1 AGENT2 ...`
  - `AGENT` 可以是內建別名（如 `auto`、`greedy`、`random`、`rulebot`），也可以是 `package.module:ClassOrFactory` 形式的匯入路徑；可用 `顯示名稱=目標` 指定輸出時的名稱。

- 常用選項：

  - 參賽者：位置引數依序輸入參賽 bot，可混合使用內建別名與自訂 factory。
    - 內建別名：`auto`、`greedy`、`random`、`rulebot`（亦接受 `greedybot`、`randombot`、`rule`）。
    - 自訂 factory：`模組路徑:Callable`，例如 `bots.greedy:GreedyBotStrategy` 或
      `my_pkg.agents:build_agent`。若要自訂顯示名稱可加上 `名稱=模組:Callable`。
  - `--hands`：每場局數，未指定 `--jangs` 時預設 16。
  - `--jangs`：每場將數（一將四圈）；可另用 `--hands` 設局數上限，連莊可能延長場次。
  - `--matches`：同一組合重複對局次數，預設 1。
  - `--seed`：整體隨機種子（座位洗牌、對局種子）；相同種子可重現整個聯賽。
  - `--scoring-profile`（別名 `--profile`）：選擇 `configs/scoring/profiles/` 的台數表。
  - `--rule-profile`：選擇 `configs/rules/profiles/` 的花牌、尾牌等規則。
  - `--base-points` / `--tai-points`：底分／每台分數，預設 100／20。
  - `--json-out`：將彙整後的統計輸出為 JSON，內容含執行設定與各 bot 指標。
  - `--quiet`：只輸出最後的排名表，不逐場列印戰果。

  腳本會針對所有 `agents` 的組合進行對戰。例如以下命令會在四種策略間進行
  所有四人組合，每組打兩場、每場 32 手：

  ```bash
  python scripts/eval_league.py \
      --hands 32 --matches 2 --seed 2024 \
      auto greedy random rulebot
  ```

  每場結果會印出最終得分，全部完成後依平均場分排序。
  四個參賽者只有一個四人組合；上述例子每個參賽者打兩場、合計 64 局。

  若有指定 `--json-out results/league.json`，會額外產生可機器解析的摘要，方便串接
  後續統計或可視化工具。

  - 範例：
    - `python scripts/eval_league.py --hands 1 greedy random rulebot auto --matches 1 --seed 1 --quiet`

## bench_sim.py
- 用途：以指定 bot 與規則進行大量自動模擬，量測環境與（可選的）計分效能。
- 基本用法：
  - `python scripts/bench_sim.py -n 1000`：執行 1,000 手模擬並輸出平均手數、吞吐量等統計。
- 常用選項：
  - `-n/--hands`：模擬手數，預設 1,000。
  - `--bot`：選擇指定 bot（`auto`、`greedy`、`random`、`rulebot`）。
  - `--seed`：設定隨機種子，確保重現性。
  - `--skip-scoring`：跳過計分階段，只測量環境模擬速度。
  - `--scoring-profile`：選擇 `configs/scoring/profiles/` 的台數表（無 `--profile` 別名）。
  - `--rule-profile`：選擇 `configs/rules/profiles/` 的花牌、尾牌等規則。
  - `--json-out`：將模擬結果輸出為 JSON，方便記錄或比較。
  - `--no-progress`：隱藏進度列。
- 範例：
  - `python scripts/bench_sim.py -n 5000 --bot random --seed 42 --skip-scoring`

## tune_greedy_weights.py

以四位 Greedy 玩家做多次局部搜尋，選出流局率最低的啟發式權重。
`--seed` 可重現搜尋流程，但不同候選使用不同對局種子，不是共用種子的配對比較。
這個目標不是勝率，也不能直接證明與其他策略對戰時較強。

```bash
python scripts/tune_greedy_weights.py --hands 256 --trials 10 --seed 42
```

- `--hands`：每次候選評估局數，預設 256；`--trials`：搜尋重啟次數，預設 10。
- `--max-steps`：每次搜尋最多步數，預設 25；`--grid-step`：搜尋間距，預設 1。
- `--scoring-profile`（別名 `--profile`）與 `--rule-profile`：計分表與規則。
- `--structure-weight-range`、`--bad-shape-weight-range`、`--isolated-weight-range`、
  `--availability-weight-range`、`--isolated-cap-range`：使用 `min:max` 或逗號清單指定範圍。
- `--json-out`：保存各次搜尋結果；`--no-progress`：隱藏進度列。

bench／league／tune 不提供 `--scoring-json`、`--no-flowers` 或尾牌直接覆寫旗標；
自訂規則透過 rule profile。`analyze_breakdown_flags.py` 的 `--scoring-json` 只決定分析旗標。
