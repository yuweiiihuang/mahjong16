# 牌譜保存、續局與重播

網頁自動保存單人與多人對局。玩家可從右上角的「牌局紀錄／續局」看統計、恢復牌桌或重播；
管理者可在本機驗證、匯出或備份私有牌譜。

## 網路牌桌自動保存

從專案根目錄啟動。未指定 `--record-db` 時，預設使用 `data/hands.sqlite3`。

```bash
uv run --locked python -m app.web --port 8000 --record-db data/hands.sqlite3
```

首次發牌就開始保存。每個接受的步驟會在回應前提交，終局與累計分在同一筆交易提交。
保存失敗回傳 HTTP 503 並凍結該桌，排除問題後可恢復到最後成功保存的位置。
資料庫狀態為 `active`、`completed` 或 `interrupted`。中斷前綴匯出為 `incomplete`，不算流局或輸局。

一份資料庫只供一個服務程序寫入。測試牌桌請另用一份資料庫。SQLite 及匯出檔都有暗牌與牌牆，
應存於網站公開目錄外。POSIX 匯出檔限擁有者讀寫，Windows 應使用受限 ACL 的目錄。

## 網頁續局與重播

- **查看紀錄**。右上角的「牌局紀錄／續局」按對局整理分數、統計、逐局結算和重播。
  和牌／自摸／放槍比率以已結算局數為分母，包含流局。中途換人時，統計仍按座位累計，
  逐局名稱則使用當時保存的名稱。
- **續局**。單人選「繼續此對局」，多人用「返回牌桌」。目前牌桌若因保存失敗而凍結，
  排除問題後選「恢復此對局」。同桌最新一局須有續局資訊、引擎版本相容，且本人仍保留座位。
  伺服器重啟中斷的多人對局也適用這些條件，已清理的房間僅供查閱。
  恢復涵蓋手牌、牌牆、反應、莊家、圈風、累計分
  及下一局亂數狀態。損壞或版本不符的紀錄會被拒絕。已保存的結算不會重複計分，
  多人只恢復一份共用牌桌。
- **認回座位**。匿名玩家使用原瀏覽器，清除 Cookie 後無法找回匿名座位。
  啟用可信閘道時用原帳號。換人、房主交接及斷線接手見 [多人連線](multiplayer.md)。
- **重新開桌**。下一局保留原對局和累計分。開始新對局時，每席回到 1,000 點及東風圈，
  原對局仍可查閱、接續。已有新版未完局時須先打完，切換對局不會重抽手牌。
- **重播**。只有本人參與過、已完成且相容的牌局可看結算和重播。
  可切換東南西北視角，每次只顯示所選座位看得到的牌。重播不影響目前對局，
  退出時會重取最新狀態。舊引擎紀錄可查摘要，離線驗證要用相同引擎版本。

玩家 API 只提供有權限的摘要、席位視角和結算。完整 JSON 牌譜供管理者離線使用。
各項操作、瀏覽器驗收和 API 測試見 [Web 測試指南](../tests/web/README.md)。

## 管理者指令

以下命令從專案根目錄執行。匯出與備份會拒絕覆寫既有檔案。

```bash
uv run --locked python -m app.replay list --db data/hands.sqlite3
uv run --locked python -m app.replay export data/hand.json --db data/hands.sqlite3 --hand-id '<局ID>'
uv run --locked python -m app.replay verify data/hand.json
uv run --locked python -m app.replay backup data/hands-backup.sqlite3 --db data/hands.sqlite3
```

需要一份離線測試牌譜時，可錄製一局電腦對局。

```bash
mkdir -p data
uv run --locked python -m app.replay record data/sample.json --seed 7
```

`verify` 逐步重播，核對動作、狀態和結算。已在執行的 SQLite 應使用 `backup` 取得一致快照。
還原流程見 [Docker 備份與還原](docker.md#備份與還原)。備份保存在資料卷之外，並限制存取。

## 離線決策匯出

`dataset` 輸出玩家視角 JSONL。預設只包含已完成局的真人決策。可用 `--source all` 納入
電腦、自動和來源未記錄的動作，或用 `--include-incomplete` 加入中斷前綴。

```bash
uv run --locked python -m app.replay dataset data/human-decisions.jsonl --db data/hands.sqlite3
uv run --locked python -m app.replay dataset data/all-decisions.jsonl --db data/hands.sqlite3 --source all
uv run --locked python -m app.replay dataset data/prefix.jsonl --record data/hand.json --source all --include-incomplete
```

`--hand-id` 限定 SQLite 單局。每行包含決策前的玩家可見觀察、合法操作、實際動作、
控制來源和局次／座位等追溯欄位。觀察會遮蔽他人的暗牌、暗槓、尚未成立的反應與牌牆。
舊紀錄未保存來源時標為 `unknown`。終局座位收付是結果欄位，中途可能換人，
不能當成個別玩家的收付。中斷前綴的終局收付為 `null`。

匯出前會完整重播和驗證，失敗不產生目標檔。JSON／JSONL 輸出磁碟須支援 hard link
（例如 APFS、NTFS、ext4），才能在完成後以不覆寫的方式發布檔案。

## 引擎格式與身分

- 原始碼呼叫端可在建立 `Mahjong16Env` 時傳入 `HandRecorder()`，一律用 `env.step(...)`
  提交動作，再用 `recorder.document()` 取最新局的獨立副本。呼叫 `replay_hand(document)`
  離線驗證，或透過 `app.hand_store.write_private_record` 寫私有檔案。
- 核心紀錄保存版本、引擎 SHA-256、解析後場規、初始牌牆、動作與逐步校驗。SHA-256 用來
  判斷相容與偵測不一致。相同 seed 可重現開局，重播連續牌局仍以紀錄的牌牆為準。
- Web 額外保存玩家代號、名稱快照、控制來源、接管事件及累計分。匿名映射使用 Cookie 的雜湊。
  帳號模式依 `(issuer, subject)` 找固定玩家 ID，映射隨 SQLite 備份保存。
  原始 Cookie、登入憑證及 subject 不進牌譜。詳見 [身分架構決策](adr/0001-account-player-identity.md)。

## AI 策略紀錄

`metadata.ai_levels` 保存開局強度，`recovery.ai_levels` 保存目前牌桌設定。
`decisions` 記錄實際電腦策略（`greedy` 或 `meowcats_2000`）與任何降級。
逐局圖示以實際策略為準，真人全程操作的座位沒有 AI 標記。進階 AI 的設定與行為見
[MeowCaTS](meowcats.md#網頁牌桌)。
