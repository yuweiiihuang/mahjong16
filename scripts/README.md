# scripts 使用指南

以下指令預設從專案根目錄執行，可先透過 `pip install -r requirements.txt` 安裝所需相依套件。

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
  - `--players`：桌次座位數，預設 4；`agents` 必須不少於此數量。
  - `--hands`：每場對局要打的手數，預設 16。
  - `--matches`：同一組合重複對局次數，預設 1。
  - `--seed`：整體隨機種子（座位洗牌、對局種子）；相同種子可重現整個聯賽。
  - `--profile` / `--scoring-json`：切換或覆寫台數表，沿用 `Ruleset` 的計分資產。
  - `--no-flowers`、`--dead-wall-mode`、`--dead-wall-base`：調整是否使用花牌與尾牌配置。
  - `--json-out`：將彙整後的統計輸出為 JSON，內容含執行設定與各 bot 指標。
  - `--quiet`：只輸出最後的排名表，不逐場列印戰果。

  腳本會針對所有 `agents` 的組合進行對戰。例如以下命令會在四種策略間進行
  所有四人組合，每組打兩場、每場 32 手：

  ```bash
  python scripts/eval_league.py \
      --hands 32 --matches 2 --seed 2024 \
      auto greedy random rulebot
  ```

  每場結果會印出最終得分，全部完成後會依平均場分排序並輸出 ASCII 表格：

  ```
  Agent    Matches Hands AvgPts/Match ...
  greedy   12      384   +42.7        ...
  random   12      384   -15.3        ...
  ```

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
  - `--players`：座位數，預設 4。
  - `--bot`：選擇指定 bot（`auto`、`greedy`、`random`、`rulebot`）。
  - `--seed`：設定隨機種子，確保重現性。
  - `--skip-scoring`：跳過計分階段，只測量環境模擬速度。
  - `--profile`、`--scoring-json`：指定計分 profile 或覆寫 JSON。
  - `--no-flowers`、`--dead-wall-mode`、`--dead-wall-base`：調整花牌與尾牌配置。
  - `--json-out`：將模擬結果輸出為 JSON，方便記錄或比較。
- 範例：
  - `python scripts/bench_sim.py -n 5000 --bot random --seed 42 --skip-scoring`

