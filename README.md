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
- 青禾網頁牌桌支援單人練習與最多四位真人的朋友房間，空位由電腦補上。
- 網頁自動保存私有 SQLite 牌譜，提供離線重播驗證與玩家視角 JSONL 決策匯出。
- `tests/` 內含環境、計分與手牌演算法的 pytest 覆蓋，支援快速迭代回歸。

## 快速開始

需求：Python 3.13+。建議使用 `uv` 建立與部署相同的鎖版環境：

```bash
uv sync --locked
source .venv/bin/activate  # Windows PowerShell 使用 .venv\Scripts\Activate.ps1
```

只需 CLI／Web 與 pytest 時，也可使用最小依賴：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt
```

啟用環境後，在專案根目錄執行：

```bash
python main.py --help
python main.py --seed 42 --human 0 --bot greedy --hands 8
python main.py --no-ui --hands 50 --log-dir logs/demo   # headless + CSV 摘要
pytest -q
```

鎖版環境另含 pandas 與 ipykernel；`rl/net.py` 需另外安裝適合執行主機的 PyTorch。
RL 目前是骨架，安裝依賴不代表已有完整訓練流程。

亦可使用 `python -m domain.gameplay.game_env` 進行匯入檢查或撰寫最小化實驗。

對外分享前須啟用全站通行碼：

```bash
uv run --locked python -m app.web --port 8000 --access-password-file /path/to/password.txt
```

通行碼檔案須放在專案與網頁目錄之外，限制只有服務帳號可讀，至少 16 字元；
建議使用隨機長密碼。網頁內輸入通行碼後，登入保留一天；網頁及所有 API
皆需驗證。自動化工具仍可用帳號 `friend` 的 HTTP Basic 驗證。
僅透過 HTTPS 隧道對外提供服務；未指定檔案時維持本機免登入模式。

Docker 建置、本地驗證與 Windows 部署／回復方式見 [Docker 牌桌](docs/docker.md)。

### Codex 本機環境與工作樹

先在本機安裝 `uv`；需要分享牌桌時另安裝 `cloudflared`。
`.codex/environments/environment.toml` 的設定指令碼會在建立新工作樹時執行
`uv sync --locked`，依 `.python-version` 與 `uv.lock` 建立獨立 `.venv` 並安裝依賴。
既有工作樹也可在專案根目錄手動執行同一指令。
本機牌桌與遠端連線由動作按鈕手動啟動；多個工作樹不能同時占用 8000 埠。
「啟動本機牌桌」按鈕的預設命令未設定通行碼，僅供本機使用。
分享前，先停止該本機測試服務，以前述 `--access-password-file` 命令啟動同一埠，
在未登入的瀏覽器確認顯示通行碼頁，再開「遠端連線」。HTTPS 隧道本身不提供登入驗證。
停止或重啟服務會清除記憶體牌局，請先結束對局；新增測試服務則指定不同埠與資料庫。

## 電腦網頁牌桌

本專案的主要 Web UI 為「青禾」桌面：簡約青綠風格的繁體中文牌桌，
單人練習搭配三位 Greedy 電腦玩家；「朋友連線」可建立房間並分享邀請網址。
朋友房間最多四位真人，空位由電腦補上，詳見 [朋友連線](docs/multiplayer.md)。

```bash
source .venv/bin/activate
python -m app.web --port 8000
```

瀏覽器開啟 `http://127.0.0.1:8000`。點選手牌後按「出牌」、雙擊牌面或按 Enter 出牌。
吃／碰／槓／胡／過依合法操作顯示，支援自動補花、聽牌、對局紀錄、聽牌候選與未見張數、台數明細及四家點數結算。
「下一局」保留累積點數，依結果連莊、輪莊與推進圈風；「重新開桌」重設為每人 1,000 點。
主要布局以電腦為主；手機也採橫向牌桌、單排手牌。直向持機時顯示旋轉提示，
橫向時隱藏房間側欄並縮減控制列。

伺服器預設綁定 `127.0.0.1`，使用瀏覽器 cookie 隔離身分；房間、進行中的牌局
與桌內累積點數存在單一程序記憶體，重啟後清除，不支援跨裝置帳戶或重啟續局。
CLI 啟動網頁時預設將私有牌譜保存至 `data/hands.sqlite3`，可用 `--record-db` 指定位置；
牌譜含暗牌與牌牆，只供管理者離線存取，重啟後仍保留。每個測試服務使用不同資料庫，
同一資料庫只允許一個服務程序寫入。詳見 [牌譜保存與匯出](docs/hand-recording.md)。
介面字型使用系統字型；牌面以本地 SVG 紋理搭配 Three.js 立體牌體繪製，
四家共用同一相機、實際尺寸與桌面光影。瀏覽器需支援 WebGL。

後續 Web UI 開發統一沿用 `ui/web/` 的桌面設計與 `app/web.py` 入口，
不再維護其他並行版型。舊版已封存，詳見 [Web UI 封存紀錄](docs/webui-archive.md)。

## 專案結構

```text
mahjong16/
├─ domain/
│  ├─ analysis.py       # 觀察資料分析 helper（剩餘牌數、丟牌模擬）
│  ├─ gameplay/         # env、摸打回合、反應判定、PlayerState、花牌
│  ├─ table/            # 座次/圈風初始化 helper
│  ├─ tiles/            # 牌面常數、牆牌建構、字串轉換
│  ├─ rules/            # Ruleset 與胡牌/聽牌判斷
│  └─ scoring/          # 台數管線（engine/state/rules/lookup）
├─ app/
│  ├─ web.py            # 青禾網頁牌桌與本地 API
│  ├─ web_rooms.py      # 朋友房間、座位與同步
│  ├─ hand_store.py     # 私有 SQLite 牌譜保存
│  ├─ replay.py         # 離線錄製、重播驗證與匯出 CLI
│  ├─ training_export.py # 玩家視角 JSONL 決策匯出
│  ├─ runtime.py        # Demo 主 loop、UI 更新與結算整合
│  ├─ table.py          # TableManager：圈風、連莊與多局管理
│  ├─ strategies.py     # Human / Auto / Greedy 策略橋接 bots
│  └─ logging.py        # 欄位化手局紀錄（CSV）
├─ ui/
│  ├─ web/              # 主要 Web UI：HTML、CSS、JS、3D 牌面與素材
│  ├─ console.py        # Rich 互動介面（提示行動、展示河牌/剩餘張數）
│  └─ rich_helpers.py   # Rich 組件共用工具
├─ bots/                # 範例策略（RandomBot、RuleBot、Greedy）
├─ rl/                  # 自對弈與訓練骨架（buffer/net/selfplay）
├─ tests/               # pytest suites（env、scoring、domain helpers）
├─ scripts/             # 聯賽、效能、戰報分析與 Greedy 調參
├─ configs/
│  ├─ rules/profiles/    # 規則開關
│  └─ scoring/          # 計分 profiles、labels、notes、constraints 與 metadata
├─ AGENTS.md            # 協作規範與提交建議
└─ README.md
```

## CLI 與資料紀錄

### `main.py` 旗標一覽

- `--seed <int>`：指定 RNG 種子，預設為隨機。
- `--human <0-3|none>`：指定玩家座位；輸入 `none`/`-1`/`no` 表示全 bot，預設無真人。
- `--bot {auto,greedy,human}`：非真人座位採用的策略，預設 `greedy`。
- `--hands <int>`：局數上限；`-1` 代表打到有人破產為止，0 或 < -1 會被拒絕。
- `--jangs <int>`：打指定將數（一將四圈）；0 為停用，不可與有限 `--hands` 同用。
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
- 前端回歸執行 `node --test tests/web/*.mjs`；實際拖拉、WebGL 與手機觸控仍需
  [瀏覽器驗收](tests/web/README.md)，不能以 Node 通過代替。

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

## 文件導覽

| 任務 | 文件 |
| --- | --- |
| 多人操作、重連與服務限制 | [朋友連線](docs/multiplayer.md) |
| 牌譜、備份、重播與研究匯出 | [牌譜指南](docs/hand-recording.md) |
| Docker／Windows 部署與回復 | [Docker 牌桌](docs/docker.md) |
| Caddy／Authelia 測試與切換前提 | [前置驗證部署](docs/gateway.md) |
| 聯賽、效能與調參 | [scripts 指南](scripts/README.md) |
| Web 回歸與人工驗收 | [測試指南](tests/web/README.md) |
| iPhone 安全區與研究限制 | [安全區筆記](docs/iphone-table-safe-area.md) |
| 模組依賴 | [架構圖](docs/architecture/diagram.png)（[Graphviz 來源](docs/architecture/diagram.gv)） |
| 外部場規參考 | [台數整理](docs/台灣麻將台數計算表.md)；以現行 JSON 與引擎為執行依據 |

## 授權與問題回報

目前 repository 尚未宣告專案原始碼授權；第三方素材授權不代表整個專案的授權。
Three.js、SortableJS 授權位於 `ui/web/vendor/`；牌面來源與修改見
[SVG 來源](ui/web/assets/tiles/fonts/README.md)，維基轉載另依其檔案中的 CC BY-SA 標示。
需要再散布或其他使用授權時，先向維護者確認。

回報問題時請附程式版本、重現命令或操作、預期／實際結果；瀏覽器問題另附裝置與版本。
透過本專案既有協作管道回報，不附通行碼、cookie 或含暗牌的私有牌譜。
目前未在文件指定公開支援信箱或專用漏洞回報管道。

## 後續方向

- 建立可比較的模擬效能基準；`scripts/bench_sim.py` 與 `scripts/eval_league.py` 已可使用。
- 擴充更強的策略樣板（MCTS、模擬式搜尋）並串接 `bots/`。
- 在 `rl/train.py` 實作正式的訓練 loop 與記錄分析管線。
