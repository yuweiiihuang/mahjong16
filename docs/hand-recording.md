# 離線牌譜紀錄與驗證

已完成引擎紀錄、版本化 JSON 格式、離線重播，以及 SQLite 網頁自動保存。
已提供玩家視角的 JSONL 決策匯出；玩家跨次戰績、RL 轉移與重啟續局仍未實作。

## 網路牌桌自動保存

```bash
.venv/bin/python -m app.web --port 8000 --record-db data/hands.sqlite3
.venv/bin/python -m app.replay list --db data/hands.sqlite3
.venv/bin/python -m app.replay export /tmp/hand.json --db data/hands.sqlite3 --hand-id <局ID>
.venv/bin/python -m app.replay verify /tmp/hand.json
.venv/bin/python -m app.replay backup /tmp/hands-backup.sqlite3 --db data/hands.sqlite3
```

`--record-db` 預設為 `data/hands.sqlite3`，CLI 啟動的牌桌會自動保存練習與朋友對局。
多個測試伺服器需指定不同資料庫；同一資料庫只允許一個服務程序寫入。
資料庫、匯出及備份路徑不能位於網站公開目錄，`data/` 已由 Git 忽略。
私有 JSON 在 POSIX 系統以僅擁有者可讀寫的權限建立；Windows 需使用受限目錄 ACL。
建立房間不會先錄製待機局面，真正開局才建立紀錄。

每個成功接受的步驟在回覆前提交，終局步驟與桌內結算/累計分在同一次交易提交。
保存失敗會回報 HTTP 503 並凍結該桌，不繼續出牌或在稍後補寫未被確認的操作；
需管理者排查並重啟服務。
SQLite 的資料庫交易保證保存前綴一致，但不會將引擎記憶體和資料庫變成同一交易。
其他健康牌桌可繼續運作；若磁碟整體失效，其他桌下一次寫入也會暫停。

保存內容新增桌 ID、局次、UTC 時間、玩家名稱快照與隨機代號、
操作來源（human/bot/auto_pass/auto_ting）、接管事件和桌內累計分。
隨機代號不含 cookie/session token，不是跨裝置帳號。
斷線座位由 bot 代打時，操作來源記為 bot；中途換人另外記接管事件，
不以最後座位持有人代表整局玩家。

資料庫的生命週期狀態為 `active`、`completed`、`interrupted`。
重新開桌、房間到期或重啟服務，未完成局保留為中斷前綴；
匯出的核心牌譜仍為 `incomplete`，不能算成流局/輸局或自動恢復成房間。
備份使用 SQLite backup API，可在服務運行時操作，不直接複製寫入中的檔案。
備份與匯出拒絕覆寫既有目標；重要備份需複製到另一個儲存位置。

第一版用單一 hands 表保存完整 JSON，每步重寫目前這一局，沿用已驗證格式。
這是少量朋友對局的簡化；若實測寫入成本過高，再把 steps 拆成逐筆資料表。
不提供網頁下載完整私有牌譜的 API。

## 訓練資料匯出

```bash
# 預設：所有完成牌局中的真人操作。
uv run --locked python -m app.replay dataset data/human-decisions.jsonl --db data/hands.sqlite3
# 包含 bot/自動/未知來源，或只讀一份離線牌譜。
uv run --locked python -m app.replay dataset data/all-decisions.jsonl --db data/hands.sqlite3 --source all
uv run --locked python -m app.replay dataset data/prefix.jsonl --record /tmp/hand.json --source all --include-incomplete
```

`--hand-id` 可指定 SQLite 中的單局。來源可選 human、bot、auto_pass、auto_ting、unknown、all。
不含來源紀錄的舊版/引擎牌譜標為 unknown，不猜成真人。
預設排除未完成局；`--include-incomplete` 納入已保存前綴，最終收付分為 null。
每份牌譜需先通過完整重播驗證，操作來源的步驟/座位亦需一致；驗證失敗不建立輸出。
不改 domain 程式碼，因此此匯出器不改變先前牌譜的引擎指紋。

JSONL 每行一筆實際提交的決策，包括：

- `observation`：決策前玩家自己的手牌/摸牌、副露、公開牌河、各家牌數/花牌/宣告狀態、
  風位、莊家與本人合法操作。對手暗槓牌面遮蔽，沒有牌牆、其他人的暗牌、
  隱藏反應資格/已提交選擇，也不使用會暴露暗槓身份的引擎 live_public 計數。
- `action`、`source`、`has_choice`：實際操作、控制來源及是否有多種合法操作。
  action 使用當時合法操作的標準表示，補齊歷史預設欄位，聽牌 waits 由引擎重建，
  不複製原始請求附帶的未驗證資料。
  被高順位蓋過的吃仍是實際選擇；未回覆者不會被補成 PASS 樣本。
- 局 ID、桌 ID、步驟、座位、玩家代號、反應窗口、格式/引擎版本與牌局狀態。
  這些是追溯欄位，不是模型可見觀察；不匯出玩家名稱或 cookie。
- `final_seat_payment`：該座位整局收付分，屬於未來結果標籤，不能放入模型輸入。
  同一座位可能換人或被 bot 接管，不能直接當成某個人的 reward。

尚不產生 next_obs、RL reward、同玩家轉移或最優動作標籤。
訓練/驗證切分至少以整局為單位，避免同一局不同決策跨到兩組。
資料先在記憶體驗證後寫入，適用少量朋友對局；大量資料時再改成暫存串流輸出。
匯出是私有離線檔案，沿用公開目錄拒絕、POSIX 0600 及不覆寫保護。
JSON/JSONL 先寫入同目錄私有暫存檔，完成後才以不覆寫的 hard link 發布。
寫入失敗不留下部分的目標檔；強制終止可能留下隱藏的暫存檔，可在程序停止後清理。
輸出磁碟需支援 hard link（例如 APFS、NTFS、ext4），不支援時回報失敗。

## 本機使用

使用專案虛擬環境，或將以下 `.venv/bin/python` 換成 `uv run --locked python`。

```bash
.venv/bin/python -m app.replay record /tmp/mahjong-hand.json --seed 7
.venv/bin/python -m app.replay verify /tmp/mahjong-hand.json
```

record 錄製並驗證一局 GreedyBot 對局，拒絕覆寫已有檔案。
verify 重新發牌、依序執行動作，檢查每一步狀態及完成局的計分明細/收付分。
這是引擎驗證，不是網頁重播播放器。

## 接入引擎

```python
import json
from pathlib import Path
from domain.gameplay.game_env import Mahjong16Env
from domain.gameplay.recording import HandRecorder, replay_hand
from domain.rules.ruleset import Ruleset

recorder = HandRecorder()
env = Mahjong16Env(Ruleset(), seed=7, recorder=recorder)
env.reset()
# 依正常路徑呼叫 env.step(action, pid=pid)，不直接修改 env 的牌局狀態。
document = recorder.document()
with Path('/tmp/hand-prefix.json').open('x', encoding='utf-8') as handle:
    json.dump(document, handle, ensure_ascii=False)
replayed = replay_hand(document)
```

每次 reset 新增一份紀錄，`document()` 回傳最新局的獨立 JSON 副本。
基礎 `HandRecorder.records` 保留本次 recorder 的所有局，只在記憶體中。
WebTable 的持久化 recorder 只保留目前一局，舊局留在 SQLite。
未提供 recorder 的既有呼叫不增加紀錄或計分工作。

## 格式與界線

- 記錄格式版本、實際 domain 原始碼 SHA-256、解析後規則、實際計分表、局 ID。
- 保存完整初始牌牆與風位/莊家設定，不依賴 seed 還原連續牌局的亂數進度。
- 初始狀態含發牌/補花結果；每一步記 actor、action、反應窗口、前後狀態校驗值、
  引擎 reward、裁決結果及窗口提前結束時未回覆的座位。
- 完成局保存原有計分引擎算出的台數、明細和收付分。
  `rewards` 是 env.step 的原始回傳，並不等於最終收付分或已定義的 RL reward。
- 輸出是私有完整牌譜，含暗牌及牌牆，不能放在 ui/web 或送進玩家 snapshot。
- 核心格式不含身份與控制來源；網頁保存的 `metadata` 增補應用層資訊。
  dataset 可匯出玩家可見觀察；RL next_obs 尚未產生，不能把下一個 actor 的觀察當成同玩家轉移。
- `incomplete` 只代表已錄下的步驟前綴，不能算成流局、輸局或可恢復房間。
- 重播只接受相同格式與 domain 原始碼版本；SHA-256 用來識別版本與偵測不一致，
  不是簽章，也不是防止惡意偽造牌譜的認證機制。
- 啟用紀錄時，只接受合法操作；偵測到直接修改引擎狀態則拒絕繼續記錄。
  自訂程式需要在 reset 的正常發牌流程安排局面，不應錄製途中偷偷改牌。

詳見 [後續規劃](architecture/game-recording-plan.md)。
