# mahjong16 — 台灣 16 張麻將環境骨架

`mahjong16` 提供可擴充的台灣 16 張麻將模擬環境，協助研究 AI 對局、策略搜尋與強化學習。核心模組保持純函式與可測性，周邊程式提供 CLI 範例、bot 策略與訓練骨架。

## 功能特色

- **16 張 drawn 環境與桌局管理**：`core.env.Mahjong16Env` 實作發牌、摸牌、反應與回合流程；`app.table.TableManager` 追加多局輪莊、圈風推進與連莊計數。
- **反應優先權與插房處理**：棄牌後依距離與「胡 > 槓 > 碰 > 吃」排序查詢，支援搶槓、補槓與聽牌鎖定。
- **尾牌留置與流局**：支援固定尾牌或「一槓一」模式；牆不足時自動流局並保留計算狀態。
- **型別化觀察與分析**：`core.types` 定義 Action/Observation schema，`core.analysis` 提供純函式觀察分析，利於 UI、bots 與測試共用。
- **模組化計分引擎**：`core/scoring` 拆分狀態整理、規則管線與 breakdown 聚合，可替換 JSON 計分表或覆寫規則。
- **CLI Demo 與紀錄工具**：`main.py` 呼叫 `app.runtime.run_demo` 提供 Rich UI、headless 進度列與 CSV 日誌 (`app.logging.write_hand_log`)；可指定手數、起始分與 bot 策略。
- **強化學習腳手架**：`rl/` 包含簡易網路、Replay Buffer 與自我對弈流程，對接核心環境即可擴充訓練方案。

## 快速開始

```bash
pip install -r requirements.txt
python main.py                # CLI 範例（預設 Rich UI）
python main.py --no-ui --hands 10 --log-dir logs  # Headless 模式 + CSV
pytest -q                     # 執行回歸測試
```

建議以 `python -m 模組` 方式啟動自訂腳本，例如：

```bash
python -m core.env            # 確認環境可匯入
python -m scripts.bench_sim --n 10000
```

## 重構後模組導覽

```text
mahjong16/
├─ core/                              # 規則、模擬與資料型別核心
│  ├─ analysis.py                     # 觀察分析 helpers（純函式）
│  ├─ env.py                          # Mahjong16Env（reset / step / legal_actions）
│  ├─ hand.py                         # 五面子一眼判定、聽牌搜尋
│  ├─ ruleset.py                      # 場規設定（尾牌、計分 profile 等）
│  ├─ tiles.py                        # 牌編碼、洗牌與格式化
│  ├─ types.py                        # Action/Observation TypedDict 定義
│  └─ scoring/
│     ├─ engine.py                    # score_with_breakdown、compute_payments
│     ├─ breakdown.py                 # 台數累加器與輸出格式
│     ├─ state.py                     # 計分所需衍生狀態
│     ├─ rules/                       # 花牌、門清等規則節點
│     ├─ tables.py                    # JSON 計分表載入與覆寫
│     ├─ types.py                     # ScoringContext / PlayerView 型別
│     └─ utils.py & common.py         # 共用工具（番種判定、分類）
├─ app/                               # CLI demo 與互動策略
│  ├─ runtime.py                      # Gameplay loop、UI 更新、計分整合
│  ├─ table.py                        # TableManager：多局流程控制
│  ├─ strategies.py                   # Auto/Human/Greedy 策略封裝
│  ├─ formatting.py                   # Rich UI 格式化工具
│  └─ logging.py                      # 手局摘要 CSV 輸出
├─ ui/
│  ├─ console.py                      # Rich 終端 UI（公資訊 / 攤牌 / 統計）
│  └─ rich_helpers.py                 # Rich 元件共用工具
├─ bots/                              # 範例 bot 策略
│  ├─ greedy.py
│  ├─ random_bot.py
│  └─ rulebot.py
├─ rl/                                # 自我對弈與訓練骨架
│  ├─ buffer.py
│  ├─ net.py
│  ├─ selfplay.py
│  └─ train.py
├─ tests/                             # pytest 回歸套件
│  ├─ conftest.py                     # 共享 fixtures
│  ├─ test_env_basic.py / test_gangs.py / ...
│  └─ scoring/                        # scoring 引擎拆分測試
│     ├─ test_engine_regression.py
│     ├─ test_breakdown.py
│     ├─ test_rules.py
│     └─ test_state.py
├─ scripts/                           # 評估、壓測工具
│  ├─ eval_league.py
│  └─ bench_sim.py
├─ main.py                            # CLI Demo 入口（argparse）
└─ taiwanese_mahjong_scoring.json     # 計分 profiles 與標籤
```

## 重構亮點

- `core.types`、`core.analysis` 將觀察與操作 schema 集中管理，減少跨模組耦合。
- 計分流程拆分為 `state -> rules -> breakdown` 三層；可針對單一步驟撰寫測試或插入自訂規則。
- CLI demo 新增 `TableManager`、headless 進度列與 CSV 記錄，方便跑大量自動對局。
- 測試新增 `tests/scoring` 子套件覆蓋衍生狀態、規則節點與累計台數。

## 測試與開發建議

- 變更核心規則或計分前，請先執行 `pytest -q`；新增番種時補上 regression case。
- 若修改 `taiwanese_mahjong_scoring.json`，確認鍵名仍符合 `core/scoring/tables.py` 需求。
- Bot 或 RL 實驗請使用 `Mahjong16Env(seed=...)` 或 `app.table.TableManager(..., seed=...)` 提供可重現的亂數。

## 待辦事項

- 補齊槓牌相關台數（暗槓/加槓/搶槓）的可配置化規則與測試。
- 增加更強的策略樣板（Monte Carlo、Simple Search）與自動評估腳本。
- 完成 `rl/train.py` 範例訓練流程並串接記錄檔分析。
