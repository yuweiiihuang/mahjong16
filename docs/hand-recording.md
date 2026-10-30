# 離線牌譜紀錄與驗證

已完成引擎紀錄、版本化 JSON 格式、離線重播，以及 SQLite 網頁自動保存。
已提供玩家視角的 JSONL 決策匯出與選用的固定帳號識別；
提供最近 100 局紀錄、完成局逐步重播，以及含續局資訊牌譜的中斷恢復；
RL 轉移仍未實作。

## 網路牌桌自動保存

以下命令從專案根目錄執行；CLI 會建立資料庫目錄。
離線範例使用 Git 忽略的 `data/`，輸出檔已存在時需另換名稱。

```bash
.venv/bin/python -m app.web --port 8000 --record-db data/hands.sqlite3
.venv/bin/python -m app.replay list --db data/hands.sqlite3
.venv/bin/python -m app.replay export data/hand.json --db data/hands.sqlite3 --hand-id <局ID>
.venv/bin/python -m app.replay verify data/hand.json
.venv/bin/python -m app.replay backup data/hands-backup.sqlite3 --db data/hands.sqlite3
```

`--record-db` 預設為 `data/hands.sqlite3`，CLI 啟動的牌桌會自動保存練習與朋友對局。
多個測試伺服器需指定不同資料庫；同一資料庫只允許一個服務程序寫入。
資料庫、匯出及備份路徑不能位於網站公開目錄，`data/` 已由 Git 忽略。
私有 JSON 在 POSIX 系統以僅擁有者可讀寫的權限建立；Windows 需使用受限目錄 ACL。
建立房間不會先錄製待機局面，真正開局才建立紀錄。

每個成功接受的步驟在回覆前提交，終局步驟與桌內結算/累計分在同一次交易提交。
保存失敗會回報 HTTP 503 並凍結該桌，不繼續出牌或在稍後補寫未被確認的操作；
排除保存問題後可從「右上角牌局紀錄圖示」恢復最後成功提交的前綴；
健康的目前 Session 不提供重複接續；凍結時則提供「恢復此 Session」。
不補寫保存失敗、未被確認的操作。
SQLite 的資料庫交易保證保存前綴一致，但不會將引擎記憶體和資料庫變成同一交易。
其他健康牌桌可繼續運作；若磁碟整體失效，其他桌下一次寫入也會暫停。

保存內容新增桌 ID、局次、UTC 時間、玩家名稱快照與隨機代號、
操作來源（human/bot/auto_pass/auto_ting）、接管事件和桌內累計分。
隨機代號不含 cookie/session token，不是跨裝置帳號。
選用可信閘道帳號模式後，隨機 UUID 由 `(issuer, subject)` 的私有持久映射取得，
同一帳號的新牌譜會跨房間／裝置保持一致；原始識別與登入憑證不存進牌譜。
映射表與 hands 共用同一個私有 SQLite，既有 backup 會一併保存。
既有匿名牌譜保持原樣，不依名稱猜配帳號。未啟用整合時維持原隨機代號。
斷線座位由 bot 代打時，操作來源記為 bot；中途換人另外記接管事件，
不以最後座位持有人代表整局玩家。

資料庫的生命週期狀態為 `active`、`completed`、`interrupted`。
重新開桌、房間到期或重啟服務，未完成局保留為中斷前綴；
匯出的核心牌譜仍為 `incomplete`，不能算成流局/輸局。
新牌譜另外保存牌桌管理、座位、偏好與亂數狀態；透過介面明確選擇續局後，
先完整重播驗證，再建立共享牌桌。舊牌譜缺少這些資訊時不猜測恢復。
備份使用 SQLite backup API，可在服務運行時操作，不直接複製寫入中的檔案。
備份與匯出拒絕覆寫既有目標；重要備份需複製到另一個儲存位置。
Windows 每小時備份在新備份通過完整性檢查後，保留最近 48 小時的全部備份；
較舊的每天保留最新一份，最長保留 30 天。清理只處理標準命名的完整備份，
不刪除 `.partial`、其他檔案或連結。

第一版用單一 hands 表保存完整 JSON，每步重寫目前這一局，沿用已驗證格式。
這是少量朋友對局的簡化；若實測寫入成本過高，再把 steps 拆成逐筆資料表。
不提供網頁下載完整私有牌譜的 API。`GET /api/history` 只回傳參與者的摘要，
`GET /api/replay?hand_id=...` 只回傳已完成、相容版本的座位視角快照；
原參與者可用 `view=0..3` 選擇四家視角；未指定時使用本人原座位。
每次只傳所選座位的手牌，其他三家暗牌／暗槓保持遮蔽，快照不含牌牆。
歷史仍依固定玩家 ID 篩選，選擇視角不能繞過參與者授權或完成局限制。

## 訓練資料匯出

```bash
# 預設：所有完成牌局中的真人操作。
uv run --locked python -m app.replay dataset data/human-decisions.jsonl --db data/hands.sqlite3
# 包含 bot/自動/未知來源，或只讀一份離線牌譜。
uv run --locked python -m app.replay dataset data/all-decisions.jsonl --db data/hands.sqlite3 --source all
uv run --locked python -m app.replay dataset data/prefix.jsonl --record data/hand.json --source all --include-incomplete
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
mkdir -p data
.venv/bin/python -m app.replay record data/mahjong-hand.json --seed 7
.venv/bin/python -m app.replay verify data/mahjong-hand.json
```

record 錄製並驗證一局 GreedyBot 對局，拒絕覆寫已有檔案。
verify 重新發牌、依序執行動作，檢查每一步狀態及完成局的計分明細/收付分。
此命令是引擎驗證；網頁播放器從「右上角牌局紀錄圖示 → 重播」開啟。

## 接入引擎

```python
from pathlib import Path
from app.hand_store import write_private_record
from domain.gameplay.game_env import Mahjong16Env
from domain.gameplay.recording import HandRecorder, replay_hand
from domain.rules.ruleset import Ruleset

recorder = HandRecorder()
env = Mahjong16Env(Ruleset(), seed=7, recorder=recorder)
env.reset()
# 依正常路徑呼叫 env.step(action, pid=pid)，不直接修改 env 的牌局狀態。
document = recorder.document()
Path('data').mkdir(exist_ok=True)
write_private_record(Path('data/hand-prefix.json'), document)
replayed = replay_hand(document)
```

每次 reset 新增一份紀錄，`document()` 回傳最新局的獨立 JSON 副本。
範例沿用應用層的私有檔案輸出，保留公開目錄拒絕、POSIX 0600 與不覆寫保護；
Windows 仍須把 `data/` 放在受限 ACL 的目錄下。
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


## 網頁續局與重播

- 入口在右上角的「牌局紀錄／續局」圖示。介面列出單人與本人參與過的多人 Session；展開查看
  分數走勢、右側積分排名、和牌／自摸／放槍次數及比率、平均每局收付與逐局表格。
  比率以已結算局數為分母，包含流局；圖線與排名色條依該 Session 最新保存門風配色。
  說明收在資訊圖示。逐局表格提供重播及結算圖示；結算重用原和牌介面，只有返回入口，
  不會開啟下一局或改變目前牌桌；返回保留原表格位置與焦點。
  圖表提供數字局次刻度、局數軸底線與1,000點基準。懸浮或左右方向鍵查看局數，
  指示線連到局數軸、四個交點標示分數，右側卡片同步更新該局積分與排名。
  游標離開或鍵盤焦點離開時恢復最新分數並隱藏指示；下方統計仍為整個Session；
  表格欄位標題固定在各自的捲動區上方。多人紀錄同樣以 Session 展開，不另列重複的近期單局清單。
- 單人 Session 是一次共用累計分數的長期遊玩，沿用資料欄位 `table_id`。
  下一局保留 ID、分數與圈風進度；「重新開桌」建立新 ID、每家重新從 1,000 點開始，
  原 Session 仍可續打。只有胡牌／流局後、下一局未發牌時才能開新 Session。
- 第一次發牌即保存，完成第一局（包括零分流局）後正式成立；未成立不代表可以重抽。
  建立新桌時檢查該玩家所有單人 Session 的最新局，只要有未完局就拒絕。
  切換已存在的 Session 不丟棄任何起手牌，也不撤銷原桌的續局資格。
- `GET /api/sessions` 是本人所有單人與曾參與多人場次的摘要；`GET /api/session?session_id=...`
  提供指定場次的完整已結算統計，不受近期紀錄 100 局限制。兩者均不回傳暗牌與牌牆。
  多人以牌桌 `table_id` 分組，顯示房號；重新開桌後為新的 Session。
  牌桌快照提供相同的 `session_id` 供介面辨識目前牌桌；它不是存取憑證，
  查詢仍驗證目前登入身分與牌譜參與者。任何一局的參與者
  均可查看整桌的公開統計，但只有本人參與過的已完成局可開啟暗牌結算與重播。
  中途換人時統計仍按座位累計，逐局和牌者使用該局保存名稱，不回填後來接替者的名稱。
  結算後才加入的玩家可接續目前座位，但不取得上一局的暗牌結算或重播權限。
  只有最新進度仍保留本人座位且符合既有恢復條件時提供「返回牌桌」；目前健康牌桌反灰。
  伺服器記住玩家選定的單人桌；重啟或回收連線記憶體後，先恢復原桌，不另開一副牌。
- 點「繼續此桌」以 `POST /api/resume` 提交局 ID。只允許同一桌最新一局、
  目前仍保留該玩家座位、含 version-1 recovery metadata 且引擎版本完全相同的紀錄。
  歷史局只能重播，不能回溯覆寫；單人可在多個 Session 各自最新進度間切換。
  不相容或損壞的新格式紀錄會明確拒絕恢復，不偷偷重開。升級前未含續局資訊的舊紀錄
  保留供查閱；首次進入新版另建 Session，舊未完局不阻擋新版開桌。新版已保存的未完局
  仍會阻擋重新開桌，不能靠切換場次重抽。舊資料若曾在同一 ID 下重新從第 1 局開始，
  保留原有分組，不猜測拆分歷史場次；本版之後的新 Session 才保證獨立 ID。
- 恢復包含手牌、反應收集、牌牆、圈風、莊家、連莊、累計分數與下一局亂數狀態。
  完成局使用已保存的原子結算，不重加一次收付；下一局正常洗牌，不重用重播的固定牌牆。
- 多人桌只建立一份恢復實例，保留各玩家的原座位；其他玩家用原帳號／瀏覽器恢復，
  或透過原房號重新加入。離線接管仍沿用原本 90 秒規則。
- 成功提交的多人操作編號隨決策保存，重啟後的重送只確認原操作。
- 匿名模式以私有資料庫中的 Cookie SHA-256 映射保持玩家 ID，不保存原始 Cookie。
  Cookie 保留一年以支援瀏覽器關閉後返回；清除 Cookie 後無法找回匿名座位。
  帳號模式仍以可信閘道驗證後的固定玩家 ID 找回。
- 重播使用原本的 3D 牌桌，原吃碰槓位置改為單排播放器：細版進度拉桿、
  上一步／播放暫停／下一步圖示、倍速、步數、東南西北視角按鈕與退出圖示。
  初始停在開局；1× 沿用牌桌節奏設定，可選 0.5×、1×、1.5×、2×、4×。
  每步為已裁決的可見事件，內部 PASS 與未決反應不各占一步。
  手動跳轉與切換視角會暫停，終局自動停止；終局再播放會從開局開始。
  視角反白標示目前風位，切換後維持進度；其他遊戲操作停用，不能分支試打。
  重播不改變目前牌桌或發出遊戲寫入；返回時重新取得最新牌況，失敗可重試。
  多人連線持續更新與維持心跳，但觀看期間不覆蓋重播畫面；房間仍照常進行。
  不同引擎版本只顯示摘要，必須使用原版本離線驗證；不嘗試跨版本執行。
- 恢復資訊隨既有 SQLite backup 一起保存。分析應先 backup 或 fetchall 後關閉連線，
  再做慢速重播；禁止一邊持有正式 SELECT cursor 一邊逐局重播。
