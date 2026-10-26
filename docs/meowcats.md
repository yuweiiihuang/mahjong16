# MeowCaTS 外部搜尋對手

`bots.meowcats.MeowCaTSStrategy` 是可選的 POSIX 外部程序 adapter，未接入 Web、
CLI bot 別名或正式服務。Mahjong16 保持合法動作、事件、補花、尾牌與計分權威。
不需 Torch；需 Python 專案環境、Git、POSIX `patch` 及 C++17 clang++ 或 g++。
macOS 與 Linux／WSL 可用；Windows 原生 pipes 不支援。

## 來源與修改

上游：[fight5566jay/MeowCaTS_1.0](https://github.com/fight5566jay/MeowCaTS_1.0)，
固定 commit `1e6ae5320d5e0d3d3b5d017ff83e05d02b9ba162`，授權 LGPL-2.1，
授權全文保留於 `bots/native/meowcats/LICENSE`。我們的 bridge 與 compatibility patch
亦依該授權提供；原作者聲明留在下載來源中。發布修改日期：2026-10-27。
不隨 repository 發布上游完整原始碼、可執行檔或生成的 lookup tables。

維護的 `bots/native/meowcats/` 包含 bridge、明確的編譯來源清單與最小修補：
POSIX 平台選擇、虛擬解構、Tile 陣列邊界、靜態 table size 定義、未初始化的
chance flags／MCTS index，以及 debug printf 字串參數。沒有修改搜尋公式。
bridge 使用原 MCTS2／IS／TT 回合搜尋與 FlatMC `makeMoveDecision()` 反應搜尋，
在入口限制至 host 合法候選；這些是整合適配，不是完整論文重現。

## 從乾淨 checkout 建置

以下在專案根目錄執行；下載與產物均位於 ignored 目錄。
每次請選新的輸出目錄，建置拒絕覆寫既有產物，也不修改上游 checkout。

```bash
mkdir -p logs/execution-reports/meowcats-build
git clone https://github.com/fight5566jay/MeowCaTS_1.0.git \
  logs/execution-reports/meowcats-build/upstream
git -C logs/execution-reports/meowcats-build/upstream checkout --detach \
  1e6ae5320d5e0d3d3b5d017ff83e05d02b9ba162
.venv/bin/python scripts/build_meowcats.py \
  logs/execution-reports/meowcats-build/upstream \
  logs/execution-reports/meowcats-build/native
```

建置驗證來源版本與乾淨狀態、複製來源後套 patch、編譯 bridge，並從原程式生成
約 51 MiB 的 `MinLackTable_old(Sampling)`。初始化上限 300 秒；成功時檢查
`READY 1` handshake。`build-command.json`、`build.log`、`initialize.log` 留在輸出目錄。
生成 table 是原生編譯器格式，不從其他平台複製。編譯／初始化失敗時保留診斷，
修正原因後以新目錄重建。可加 `--sanitize` 建立獨立 ASan／UBSan 版本。

設定沿用 pinned upstream，固定每次 MCTS／FlatMC 2000 samples、first/per round 100、
單執行緒、IS／TT／merge 啟用、同步釋放樹，關閉 SGF 與 debug stdout。
遇暗槓／加槓候選但選棄牌時，保留原流程的第二次 discard-only 搜尋；
不能把這描述為每個決策恰好只搜尋 2000 次。

## 使用與驗證

```python
from app.training_export import player_observation
from bots.meowcats import MeowCaTSStrategy

# env 是呼叫端持有的 MahjongEnvironment；只把篩選後觀察傳給 bot。
with MeowCaTSStrategy("logs/execution-reports/meowcats-build/native/bridge",
                     "logs/execution-reports/meowcats-build/native/runtime",
                     env.rules) as bot:
    obs = player_observation(env, env.turn)
    obs["melds_all"] = [player["melds"] for player in obs["players"]]
    action = bot.choose(obs)
```

必須在目前待決策玩家的 TURN／REACTION 呼叫；`player_observation()` 之外須加上
上述 `melds_all`。adapter 只傳自己暗手／進牌、公開副露／棄牌／花牌、剩餘張數與
合法候選，並再次遮罩他家暗槓。HU 直接接受；TING 無上游對應，使用合法普通棄牌。
同牌手牌／進牌候選合併後映回原合法 dict；不會讀對手暗手或牌牆順序。

每個 context 擁有一個長駐程序，`choose()` 序列化請求；預設 handshake／決策 timeout
15 秒。錯誤、錯序、非法索引或逾時會清理程序並拋錯，不會替換成其他 bot。
`error_log` 指向 runtime 內獨立 stderr 檔；`latencies` 僅量測 IPC＋搜尋，不含
觀察建構、初始化或 HU／強制動作捷徑。呼叫端須在失敗時結束該對局，使用 context
或 `close()` 回收程序。不要讓其他使用者修改執行檔、來源或 runtime 設定。

```bash
MEOWCATS_BRIDGE="$PWD/logs/execution-reports/meowcats-build/native/bridge" \
MEOWCATS_RUNTIME="$PWD/logs/execution-reports/meowcats-build/native/runtime" \
  .venv/bin/pytest -q tests/bots/test_meowcats.py
.venv/bin/pytest -q
```

未設定環境變數時跳過原生 bridge fixtures；其餘隱私、協定與程序失敗測試仍執行。
測試不重跑牌力實驗。零星 fixtures 通過不等於所有 C++ 路徑無錯。

## 模型邊界

花牌／尾牌適配以公開資訊估計正常可摸張數：
`floor(max(0, remaining-reserved) * (remaining-unrevealed_flowers) / remaining)`，
空牆為零；reserved 包含 gang_plus_one 模式的公開槓數。
這假定花牌位置均勻，是近似，並非讀取牌牆的精確 oracle。
原生內部 rollout 仍可能使用 host 限制的動作（例如吃牌後棄牌鎖），因此合法輸出
不代表內部模擬與所有 Mahjong16 規則完全一致。原方法主要優化胡牌率，不保證淨分。
