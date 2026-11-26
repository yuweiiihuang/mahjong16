# 用 Docker Compose 自架 mahjong16

先準備 Docker Engine 和 Docker Compose。使用 Docker Desktop 的話，切到 Linux 容器模式。
Compose 會用專案的 Dockerfile 建置映像，牌譜則存在資料卷裡。

## 建置與啟動

下載原始碼。要部署特定版本的話，進入專案目錄後切到對應的提交。

```sh
git clone https://github.com/yuweiiihuang/mahjong16.git
cd mahjong16
```

在專案目錄外建立一個只有授權使用者可讀的通行碼檔，寫入一行至少 16 字元的通行碼。
接著在 `compose.yaml` 旁建立 `.env`，填入通行碼檔的絕對路徑。通行碼本身留在檔案裡。

```dotenv
MAHJONG_PASSWORD_FILE="/absolute/path/to/access-password.txt"
MAHJONG_PORT=8000
MAHJONG_IMAGE=mahjong16:local
```

`MAHJONG_PORT` 設定主機埠，預設是 8000。`MAHJONG_IMAGE` 設定建置和啟動用的映像標籤，
預設是 `mahjong16:local`。

在原生 Linux 上使用一般的 rootful Docker 時，容器以 UID 10001 讀取通行碼檔。
可以把檔案所有者設為 10001，權限設為 `0600`。若用 rootless Docker 或啟用了 UID 映射，
按映射後的主機 UID 設定讀取權限。

```sh
docker compose build web
docker compose up -d --no-build --pull never --wait web
```

在 Docker 主機開啟 [http://localhost:8000](http://localhost:8000) 並輸入通行碼。改過主機埠的話，
把網址裡的 8000 換掉。用 `docker compose ps` 看容器狀態，啟動失敗時用
`docker compose logs --tail 100 web` 查原因。

### 使用既有映像

如果已在自己的 registry 發布映像，把 `MAHJONG_IMAGE` 填成完整的映像名稱，包含版本標籤。
用原來的 Compose 設定和通行碼檔下載映像並啟動牌桌。

```sh
docker compose pull web
docker compose up -d --no-build --pull never --wait web
```

需要進階電腦對手時，見 [MeowCaTS 的 Docker 建置](meowcats.md#docker-發布)。

## 分享牌桌

Compose 預設只把牌桌開在 Docker 主機的 `127.0.0.1`。要讓朋友從其他裝置連線，在主機上用 HTTPS
反向代理或隧道轉發到這個埠，並保留存取驗證。需要讓朋友分別登入自己的帳號時，可加上
[Pocket ID／Passkey](pocket-id.md)。

## 更新與回復版本

換版前先備份，保留目前的映像標籤和 Compose 設定。等玩家打完再更新。取得新版本原始碼後，
在 `.env` 裡為 `MAHJONG_IMAGE` 設一個新標籤，接著建置映像並啟動牌桌。
要回到上一版，就用上一版的 Compose 設定，把 `MAHJONG_IMAGE` 改回舊標籤，再執行啟動命令。

換容器時，Compose project 名稱相同就會接回原本的 `hand-records` 資料卷。
`docker compose down` 會保留資料卷。加上 `-v` 就會一起刪除。
對局能否接續取決於牌譜和引擎版本，見 [網頁續局與重播](hand-recording.md#網頁續局與重播)。

## 備份與還原

容器把牌譜寫到 `/var/lib/mahjong16/hands.sqlite3`，牌桌開著也能做一致性備份。
備份前，先確認容器內和主機上的備份檔名都還沒用過。

下列命令以基本 Compose 部署為例。若使用 Pocket ID 或 Authelia，先確認現行 `web` 容器
掛載的是要備份的牌譜卷，再讓兩條命令沿用該部署的 Compose project、設定檔和環境設定
（依實際部署帶上 `-p`、所有 `-f` 及 `--env-file` 或環境變數）。

```sh
docker compose exec web python -m app.replay backup /var/lib/mahjong16/hands-backup.sqlite3 --db /var/lib/mahjong16/hands.sqlite3
docker compose cp web:/var/lib/mahjong16/hands-backup.sqlite3 ./hands-backup.sqlite3
```

備份裡有暗牌和牌牆。把檔案存到資料卷之外，只讓有權限的人讀取。

還原先用新的 Compose project，讓備份寫進另一個資料卷。這裡用 `mahjong16-recovery`。
把命令裡的主機路徑換成備份檔的絕對路徑，並確認容器的 UID 讀得到該檔。

```sh
docker compose -p mahjong16-recovery run --rm --no-deps -v "/absolute/path/to/hands-backup.sqlite3:/backup/hands.sqlite3:ro" web python -m app.replay backup /var/lib/mahjong16/hands.sqlite3 --db /backup/hands.sqlite3
docker compose -p mahjong16-recovery run --rm --no-deps web python -m app.replay list --db /var/lib/mahjong16/hands.sqlite3
```

若目標資料庫已存在，備份命令會拒絕覆寫。確認牌局列表後，把還原牌桌的 `MAHJONG_PORT`
設成和正式牌桌不同的值，再用同一個 project 名稱啟動。

```sh
docker compose -p mahjong16-recovery up -d --no-build --pull never --wait web
```

登入還原的牌桌，確認找得到牌局，也能重播。驗證完再停掉原本的牌桌並切換入口，
留著舊資料卷供回復。其他牌譜管理命令見 [牌譜指南](hand-recording.md)。
