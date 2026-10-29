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

鎖版環境另含 pandas 與 ipykernel；本機 BC／PPO 使用可選的 PyTorch 依賴，見下方。

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
停止前仍建議先結束對局；啟用保存的新牌譜可從「牌局紀錄／續局」恢復最後提交的狀態。
舊版或不同引擎版本的牌譜不能保證續接；新增測試服務須指定不同埠與資料庫。

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

伺服器預設綁定 `127.0.0.1`，以瀏覽器 Cookie 隔離匿名身分，或透過可信閘道使用固定帳號。
牌桌由單一程序服務；啟用保存後，新牌譜會保存恢復所需的座位、累計分數與亂數狀態，
重啟後可從「右上角牌局紀錄圖示」繼續同版本牌局。
CLI 啟動網頁時預設將私有牌譜保存至 `data/hands.sqlite3`，可用 `--record-db` 指定位置；
完整牌譜含暗牌與牌牆，只供管理者離線存取；網頁僅提供本人紀錄摘要與完成局的玩家視角重播。
每個測試服務使用不同資料庫，
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
├─ rl/                  # 安全玩家觀察、Greedy 示範、BC／單局 PPO 與獨立評估
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

## 本機 BC／PPO

這條流程使用 common／taiwan_base 規則，先模仿 Greedy，再讓一個學習座位對三個
固定 Greedy 做單局 PPO。教師、對手與模型共用已遮蔽其他玩家私有資訊的觀察；
與網頁原始觀察下的 Greedy 不保證逐步相同。它尚未整合 Web bot 選單。

```bash
uv sync --locked --extra rl
source .venv/bin/activate
mkdir -p data/rl checkpoints logs/execution-reports
python -m rl.selfplay data/rl/train.jsonl --split train --hands 100
python -m rl.selfplay data/rl/validation.jsonl --split validation --hands 20
python -m rl.train bc data/rl/train.jsonl data/rl/validation.jsonl checkpoints/bc.pt --epochs 10
python -m rl.train ppo checkpoints/bc.pt checkpoints/ppo.pt --hands 8 --updates 1
python -m rl.evaluate greedy checkpoints/bc.pt checkpoints/ppo.pt --walls 100 \
  --output logs/execution-reports/rl-validation.json
```

指令先以 CPU 執行，局數是操作示例，不是有效牌力的保證。資料、模型與報告皆受 Git
忽略；父目錄需先建立，輸出禁止覆寫及放入網站公開目錄。模型以 `choose(obs)`
回傳合法候選，但需要 RL 安全觀察，不能直接塞入傳 raw observation 的舊聯賽入口。

BC 按整局 seed 切分 train／validation／test，排除單選決策的模仿 loss 與準確率，
使用 validation loss 選模型。PPO 的中途 reward 為 0，終局為淨收付分除以 100，
gamma=1；僅使用當輪完整局，不以目前引擎的零向量作 reward。
評估主看每局／每場淨分、平均名次、胡率與放槍率，不轉成 Greedy=100 指數。
預設 `--unit hand` 評估獨立單局，每場淨分為 null、名次單位為 hand。
候選 `random` 從所有合法動作等機率抽選（含胡牌與 PASS），每個 seed／座位
使用獨立亂數；與只隨機棄牌的舊 `RandomBot` 不同。

BC 可明確加上 `--cache-dir data/rl/tensor-cache`，首次完整驗證每個來源分片後，
原子發布 CPU tensor 快取；後續 epochs 與 validation 以 memory mapping 讀取。
快取保留原本分片／batch 邊界、batch 內 Python shuffle、合法候選順序與 mask，
強制動作仍進入歷史，DAgger 歷史使用實際執行動作。快取內容不含模型中間表示。
資料、規則、前處理程式、歷史設定或 PyTorch／dtype 改變會使用新快取；分片缺失、
多出或 checksum 不符會報錯。生成資料可刪除重建，舊版快取不自動刪除，也不提交 Git。
首次建置增加耗時與磁碟用量；每次使用仍驗證來源與快取雜湊，預設不啟用快取。
Python 的 `fresh_bc`／`continue_bc`／`bc_metrics` 也可傳入 `cache_dir=Path(...)`，
讓 DAgger 聚合續訓重用既有資料分片；它不改變選模與 checkpoint 續訓契約。

`--unit jang` 使用既有 TableManager 跑完整一將，包含連莊與流局續莊，
依場末累計淨分計算名次，同分取平均名次；超過 512 局會報錯，不發布未完成場次。
每局淨分是總淨分除以總局數，每場淨分是完整場次的平均收益；胡率與放槍率均以局為分母。
胡率包含花胡；放槍率計棄牌胡／搶槓的出牌者，排除七搶一等花胡。
另保留流局率、座位與莊家結果；對 Greedy 的差值與標準誤按共同 seed 分組，
單局模式比較單局收益，一將模式比較每場收益。

```bash
# 小量完整一將評估：每個 seed 讓候選各輪四個座位。
python -m rl.evaluate greedy checkpoints/bc.pt --unit jang --walls 1 \
  --output logs/execution-reports/rl-jang-validation.json
```

一將模式中 `--walls` 表示獨立場次 seed 組數，每組會跑四場；
它不代表牌牆數，也不是把四場加在一起當一場。單局與一將結果須分開比較。

Greedy 的兩個獨立實驗版可透過評估入口比較，預設 `greedy` 不變：

```bash
python -m rl.evaluate greedy greedy-defense greedy-lookahead --unit jang --walls 8 \
  --output logs/execution-reports/greedy-variants.json
```

`greedy-defense` 只在對手宣告聽或已有四組明副露、自己至少兩個結構步驟未聽時，
以可見牌估計較低風險的棄牌；此排序不是放槍機率，也不把牌河當保證安全牌。
`greedy-lookahead` 只改反應決策，枚舉吃碰後的合法棄牌，按最佳剩餘牌形比較 PASS；
遵守吃後同牌禁打規則，槓不猜補牌，後續實際出牌仍使用原 Greedy 規則。
兩者皆為待驗證的啟發式，不代表已改善牌力；上述命令循序評估。

續訓可把 PPO checkpoint 作為 `rl.train ppo` 的輸入，寫入另一個新檔；
需保持相同 `--seed` 與 `--hands`，從完整 batch 交界恢復 optimizer 與 RNG。
續訓也需保持相同 `--device`；舊 checkpoint 視為 CPU，BC 可在選定裝置開始新的 PPO。
MPS／CUDA 會保存與恢復隨機狀態，但 GPU 浮點運算不保證逐位重現。
資料／模型的引擎、規則、計分及編碼版本必須相符。`--split test` 評估保留給固定方案，
不要根據 test 結果反覆挑 checkpoint。完整選項見各入口的 `--help`。

牌面 Transformer 使用相同安全觀察，將原編碼無損重排為 34 個牌種、4 個玩家與
1 個全局 token；3 層、128 維、4 heads，以候選動作 cross-attention 輸出策略，
另有狀態 value head。此版尚不讀取公開事件歷史。舊 MLP 與 checkpoint 仍可使用。

`--architecture hierarchical` 使用相同盤面編碼，參考
[Tjong](https://doi.org/10.1049/cit2.12298) 分別估計合法動作類型與該類型內的候選機率，
兩者相乘形成完整合法動作的聯合分布；BC、PPO 與評估使用同一分布，評估取聯合 argmax。
此為台麻適配，保留聽牌及不同吃牌組合，尚未加入 Tjong 的歷史記憶與 fan backward，
也未實作 Suphx 的 oracle guiding 或整場 reward predictor；需另訓新 BC checkpoint。

`--architecture temporal` 在分層策略上加入三層因果 Transformer，讀取目前盤面與
前三次同一玩家的可見盤面／已選動作，總共四個決策位置；每局重設記憶，
BC、PPO 與逐局／整將評估使用相同視窗。這是自己的決策歷史，不是完整公開事件序列。
資料必須保留每局全部玩家決策（包含強制動作）及從零連續的 `seq`；讀取時依玩家分流，
缺步或重排會拒絕。現有完整 Greedy 匯出可使用，只有選擇動作的抽樣資料則不可。
過去的 reward 與終局標籤不會送入 actor；舊模型依然只讀取目前盤面。

PPO 可用 `--bc-reference checkpoints/temporal-bc.pt --bc-kl-coef 0.2` 加入固定 BC
策略約束，使用完整合法候選分布的 `KL(目前策略 || BC)`，強制動作不計入策略損失。
係數預設為 0；從 BC 開始且係數大於 0 時，預設以輸入的 BC 作為 reference。
Reference 不更新，checkpoint 保存其路徑與 SHA256；續訓必須維持係數、reference
內容、seed、每批局數及裝置。此 KL 約束與原有 PPO 更新前後 KL early stop 不同。
每批另記錄實際 optimizer 步數、early stop、更新後整批採樣策略 KL／BC KL、entropy
與 critic explained variance；零回報變異時 explained variance 為 null。
`kl` 和 `bc_kl` 是最後檢查的 minibatch 值；`rollout_*` 才是完整 rollout 的統計。

Apple Silicon 可明確指定 MPS；若程序無法存取 GPU 會報錯，不會靜默退回 CPU。
Codex 沙箱可能使 MPS 偵測失敗，需在可存取 GPU 的執行環境操作。
NVIDIA GPU 可指定 `--device cuda`；需安裝相容顯卡架構的 PyTorch CUDA build，
無 CUDA 時會明確報錯。BC 權重可跨裝置開始新 PPO；既有 PPO 續訓仍須使用原裝置。

Linux x86_64／WSL 的 CUDA 12.6 環境（例如本專案的 GTX 1080 Ti）使用獨立安裝選項：

```bash
uv sync --locked --extra rl-cu126
source .venv/bin/activate
python -m rl.train bc data/rl/train.jsonl data/rl/validation.jsonl \
  checkpoints/temporal-bc.pt --architecture temporal --device cuda --epochs 20
```

`rl-cu126` 鎖定已驗證的 `torch==2.14.1+cu126`；與一般 `rl` 選項互斥。
Mac／一般環境仍用 `uv sync --locked --extra rl`。CUDA 12.6 環境後續同步也須指定
`--extra rl-cu126`，勿改用一般 `rl`，其 Linux 預設 wheel 使用 CUDA 13。
執行時直接用已啟用的 `.venv`，或 `uv run --no-sync python ...`，避免隱式同步換掉 build。

BC／PPO 可加 `--deterministic`，在程序內啟用確定性 kernel，可能降低速度；預設不強制。
CUDA 設定必須在初始化 GPU 前生效。CLI 會設定 `CUBLAS_WORKSPACE_CONFIG=:4096:8`；
已在程式中初始化 CUDA 的呼叫者，須預先設定此環境變數。checkpoint 記錄實際的
determinism 設定，PPO 續訓必須一致；舊 PPO checkpoint 視為未啟用確定性設定。
這只針對相同硬體與軟體環境，並不保證 CPU／MPS／CUDA 或不同 PyTorch 版本逐位元相同。

```bash
python -m rl.train bc data/rl/train.jsonl data/rl/validation.jsonl \
  checkpoints/transformer-bc.pt --architecture transformer --device mps --epochs 20
python -m rl.train ppo checkpoints/transformer-bc.pt checkpoints/transformer-ppo.pt \
  --device mps --hands 64 --updates 1
python -m rl.benchmark data/rl/train.jsonl --threads 4 \
  --devices cpu mps --architectures temporal \
  --output logs/execution-reports/device-benchmark.json
```

desktop 測速可改為 `--devices cpu cuda`。不指定裝置時依序測 CPU 與可用的 MPS／CUDA；
明確指定的裝置若不可用會報錯，不會靜默退回 CPU。架構可選 MLP／Transformer／
hierarchical／temporal，未指定時測全部四種；temporal 使用資料中實際決策的歷史。
測速使用相同 FP32 初始權重與真實觀察，分開報預先編碼的更新、含編碼／傳輸的更新
與單步 `choose`；含 warmup，以及 MPS／CUDA 在各計時區間前後的同步。
測速不含磁碟讀取、引擎與 Greedy 對手成本，不能視為完整訓練加速比。

## 後續方向

- 建立可比較的模擬效能基準；`scripts/bench_sim.py` 與 `scripts/eval_league.py` 已可使用。
- 擴充更強的策略樣板（MCTS、模擬式搜尋）並串接 `bots/`。
- 驗證 BC／PPO 在足夠資料與多個訓練 seed 下的收益，再評估跨局與其他對手。
