# 用 Docker Compose 自架青禾麻將

準備 Docker Engine 和 Docker Compose。使用 Docker Desktop 時，請啟用 Linux 容器。
標準部署會從專案的 Dockerfile 建置映像，將牌譜保存在 Compose 資料卷。

## 建置與啟動

下載原始碼並進入專案目錄。如果要部署指定版本，先切換到對應的提交。

```sh
git clone https://github.com/yuweiiihuang/mahjong16.git
cd mahjong16
```

在專案目錄外建立通行碼檔，寫入一行至少 16 字元的通行碼，並限制檔案存取權限。
在 `compose.yaml` 同目錄建立 `.env`。填入通行碼檔的絕對路徑，通行碼本身留在檔案裡。

```dotenv
MAHJONG_PASSWORD_FILE="/absolute/path/to/access-password.txt"
MAHJONG_PORT=8000
MAHJONG_IMAGE=mahjong16:local
```

`MAHJONG_PORT` 是主機埠，預設 8000。`MAHJONG_IMAGE` 是建置及啟動時使用的映像標籤，
預設 `mahjong16:local`。原生 Linux 若使用一般的 rootful Docker，容器會以 UID 10001
讀取通行碼。讓該 UID 擁有讀取權限，例如將檔案所有者設為 10001 並使用 `0600`。
若啟用 rootless Docker 或 UID 映射，請依實際映射調整主機上的檔案權限。

```sh
docker compose build web
docker compose up -d --no-build --pull never --wait web
```

在 Docker 主機開啟 [http://localhost:8000](http://localhost:8000)，輸入通行碼。
若改過主機埠，請使用自己的設定。可以用 `docker compose ps` 查看狀態，
或用 `docker compose logs --tail 100 web` 查啟動錯誤。

### 使用既有映像

如果你已在自己的 registry 發布映像，將 `MAHJONG_IMAGE` 設成完整的映像名稱與版本標籤。
沿用同一份 Compose 設定及通行碼檔，再執行：

```sh
docker compose pull web
docker compose up -d --no-build --pull never --wait web
```

## 分享牌桌

Compose 預設只在 Docker 主機的 `127.0.0.1` 開放。要讓朋友從其他裝置連線，
可在主機上用 HTTPS 反向代理或隧道連到這個本機埠，並保留存取驗證。
需要各自的帳號時，可加上 [Pocket ID／Passkey](pocket-id.md)。

## 更新與回復版本

更新前先備份，保留目前的映像標籤和 Compose 設定，並等玩家結束牌局。取得新版本原始碼後，
在 `.env` 設定新的 `MAHJONG_IMAGE` 標籤，再執行建置與啟動命令。
要回復時，使用上一版的 Compose 設定，把 `MAHJONG_IMAGE` 改回仍保留的舊標籤，再執行啟動命令。

沿用同一個 Compose project 名稱，容器換版會沿用 `hand-records` 資料卷。
`docker compose down` 會保留資料卷，加上 `-v` 則會連資料卷一起刪除。
對局能否接續取決於牌譜和引擎版本，見 [網頁續局與重播](hand-recording.md#網頁續局與重播)。

## 備份與還原

牌譜資料庫位於容器的 `/var/lib/mahjong16/hands.sqlite3`。牌桌運行中可執行一致性備份。
請為容器內和主機端的備份選擇尚未使用的檔名：

```sh
docker compose exec web python -m app.replay backup /var/lib/mahjong16/hands-backup.sqlite3 --db /var/lib/mahjong16/hands.sqlite3
docker compose cp web:/var/lib/mahjong16/hands-backup.sqlite3 ./hands-backup.sqlite3
```

主機端備份含暗牌與牌牆。限制檔案存取權限，並把備份保存在資料卷之外。

還原時，先用新的 Compose project 建立隔離的資料卷。以下以 `mahjong16-recovery` 為例，
將命令中的主機路徑換成備份檔的絕對路徑，讓容器 UID 可以讀取該檔：

```sh
docker compose -p mahjong16-recovery run --rm --no-deps -v "/absolute/path/to/hands-backup.sqlite3:/backup/hands.sqlite3:ro" web python -m app.replay backup /var/lib/mahjong16/hands.sqlite3 --db /backup/hands.sqlite3
docker compose -p mahjong16-recovery run --rm --no-deps web python -m app.replay list --db /var/lib/mahjong16/hands.sqlite3
```

備份命令會拒絕覆寫既有資料庫。確認牌局列表後，為還原實例設定不同的 `MAHJONG_PORT`，
沿用同一個 project 名稱啟動：

```sh
docker compose -p mahjong16-recovery up -d --no-build --pull never --wait web
```

登入還原的牌桌查看牌局與重播。確認後再停用原實例並切換入口，原資料卷可留作回復點。
牌譜管理的其他命令見 [牌譜指南](hand-recording.md)。
