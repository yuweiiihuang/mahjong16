# mahjong16 — 台灣 16 張麻將環境

`mahjong16` 面向 AI 對局與策略研究打造，提供台灣 16 張麻將規則的可重現模擬環境。
核心遊戲元件集中在 `domain/` 套件，以語意子模組拆分摸打流程、桌面狀態、牌面資料與
規則判定；周邊程式提供終端 CLI 體驗、bot 策略與 reinforcement learning 腳手架，
協助快速驗證各種對局想法。

## 主要特色

- `domain/gameplay/game_env.py` 的 `MahjongEnvironment`/`Mahjong16Env` 處理發牌、摸打、反應
  優先權（胡 > 槓 > 碰 > 吃）與流局。
- `domain.rules.Ruleset` 支援花牌開關、尾牌留置模式（固定或「一槓一」）、隨機座次與圈
  風花牌計分。
- 台數計算採分層管線：`domain/scoring/state.py` 整理衍生狀態，`domain/scoring/rules/*`
  套用番種，`domain/scoring/breakdown.py` 搭配 `configs/` 下的番種與標籤輸出明細。
- `app/runtime.py` 搭配 Rich 提供互動桌面 UI，可切換 headless 進度列並輸出 CSV 手局摘要。
- `app/strategies.py` 與 `bots/` 提供人類互動、啟發式與隨機策略骨架，方便替換自訂 AI。
- `tests/` 內含環境、計分與手牌演算法的 pytest 覆蓋，支援快速迭代回歸。

## 快速開始

需求：Python 3.13+ 與 pip。

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt

python main.py --help
python main.py --seed 42 --human 0 --bot greedy --hands 8
python main.py --no-ui --hands 50 --log-dir logs/demo   # headless + CSV 摘要
pytest -q
```

亦可使用 `python -m domain.gameplay.game_env` 進行匯入檢查或撰寫最小化實驗。

## 專案結構

```text
mahjong16/
├─ domain/
│  ├─ analysis.py       # 觀察資料分析 helper（剩餘牌數、丟牌模擬）
│  ├─ gameplay/         # env、摸打回合、反應判定、PlayerState、花牌
│  ├─ table/            # 座次/圈風初始化 helper
│  ├─ tiles/            # 牌面常數、牆牌建構、字串轉換
│  ├─ rules/            # Ruleset 與胡牌/聽牌判斷
│  └─ scoring/          # 台數管線（engine/state/rules/tables/...）
├─ app/
│  ├─ runtime.py        # Demo 主 loop、UI 更新與結算整合
│  ├─ table.py          # TableManager：圈風、連莊與多局管理
│  ├─ strategies.py     # Human / Auto / Greedy 策略橋接 bots
│  └─ logging.py        # 欄位化手局紀錄（CSV）
├─ ui/
│  ├─ console.py        # Rich 互動介面（提示行動、展示河牌/剩餘張數）
│  └─ rich_helpers.py   # Rich 組件共用工具
├─ bots/                # 範例策略（RandomBot、RuleBot、Greedy）
├─ rl/                  # 自對弈與訓練骨架（buffer/net/selfplay）
├─ tests/               # pytest suites（env、scoring、domain helpers）
├─ scripts/             # 評估/效能腳本（目前為占位等待擴充）
├─ configs/
│  ├─ profiles/
│  │  ├─ taiwan_base.json    # 預設番種台數表（其餘 profile 同目錄）
│  │  └─ …
│  ├─ labels.json            # 台數標籤對照
│  ├─ notes.json             # 台型備註
│  └─ constraints.json       # 互斥/依賴規則
├─ AGENTS.md            # 協作規範與提交建議
└─ README.md
```

## CLI 與資料紀錄

### `main.py` 旗標一覽

- `--seed <int>`：指定 RNG 種子，預設為隨機。
- `--human <0-3|none>`：指定玩家座位；輸入 `none`/`-1`/`no` 表示全 bot，預設無真人。
- `--bot {auto,greedy,human}`：非真人座位採用的策略，預設 `greedy`。
- `--hands <int>`：局數上限；`-1` 代表打到有人破產為止，0 或 < -1 會被拒絕。
- `--start-points <int>`：每位玩家的起始分數，須為正整數，預設 1000。
- `--log-dir <path>`：寫入每局 CSV 摘要的資料夾，headless 且未指定時預設為 `logs/`。
- `--no-ui`：禁用互動 Rich 介面並改以 headless 流程執行，會自動關閉真人座位。
- `--sessions <int>`：獨立桌次數量，>1 時改用批次 headless；預設 1。
- `--cores <int>`：批次 headless 最大工作程序數；省略時根據 CPU 自動判定。

Headless 模式改以進度列呈現；若 `--sessions` > 1 或 `--cores` > 1 亦會自動切至
`run_demo_headless_batch`，此時 `--no-ui` 旗標可省略。批次模式會禁用真人座位並在
必要時預設輸出到 `logs/`。

- `app/logging.py` 每局輸出座位、花牌紀錄、台數與輸贏，便於後續統計。
- 互動介面利用 `ui.console` 與 `domain.analysis` 顯示候選聽牌、剩餘枚數與反應訊息。

## 測試與品質

- 修改核心規則或計分前請執行 `pytest -q`，新增番種時務必補上 regression case。
- 需要重現隨機流程時，對 `Mahjong16Env` 或 `TableManager` 傳入 `seed`。
- 測試資料使用 `tests/helpers/tile_pool.py` 產生牆牌，避免手動 hardcode。
- `AGENTS.md` 紀錄提交與命名規範；撰寫程式時維持 PEP 8 與 4-space 縮排。

## 自訂規則與計分

使用 `Ruleset` 調整變體，再搭配 scoring 管線產生結算結果：

```python
from domain import Mahjong16Env, Ruleset
from domain.scoring.lookup import load_scoring_assets
from domain.scoring.engine import score_with_breakdown

rules = Ruleset(
    rule_profile="common",  # loads configs/rules/profiles/common.json toggles
)
env = Mahjong16Env(rules, seed=1234)
obs = env.reset()

table = load_scoring_assets(rules.scoring_profile, rules.scoring_overrides_path)
```

計分表以 `configs/scoring/profiles/` 內的 per-profile JSON 為基礎，並對應 `domain/scoring/lookup.py` 的 key。
規則開關（如 `include_flowers`、`dead_wall_mode`、花牌/風位設定）集中於 `configs/rules/profiles/<rule_profile>.json`（預設 `common.json`），由 `Ruleset.rule_profile` 注入。
若需覆寫計分表，請提供新的 JSON 路徑給 `Ruleset.scoring_overrides_path`（可指向任一 profile 檔案），並新增測試驗證。

## 後續方向

- 補齊 `scripts/bench_sim.py`、`scripts/eval_league.py` 的實作與效能基準。
- 擴充更強的策略樣板（MCTS、模擬式搜尋）並串接 `bots/`。
- 在 `rl/train.py` 實作正式的訓練 loop 與記錄分析管線。
