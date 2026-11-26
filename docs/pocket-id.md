# 用 Pocket ID 讓朋友各自登入

Pocket ID 管理帳號、邀請和 Passkey，OAuth2 Proxy 驗證登入，牌桌依帳號找回固定的玩家 ID。
只需要共用一組通行碼時，見 [Docker Compose 自架](docker.md)。身分與牌譜的關係見
[身分架構決策](adr/0001-account-player-identity.md)。

先在本機驗證。對外部署需要固定 HTTPS 網址，牌桌與帳號服務各用獨立的 origin，
並核對 OIDC issuer、callback 和 Secure cookie。公開設定產生器目前接受 `https://<主機>.ts.net`，
詳見 [Windows 與 Tailscale Funnel 範例](#windows-與-tailscale-funnel-範例)。

## 在本機試用

先啟動 Docker 引擎，並在專案目錄執行 `uv sync --locked`。以下用 shell 操作，
設定目錄須位於專案外且尚未建立。原生 Linux 要確認容器 UID 10001 能讀取必要的 bind mount。

```sh
export MAHJONG_IMAGE=mahjong16:pocket-stage
export MAHJONG_POCKET_CONFIG="$HOME/.config/mahjong16/pocket-stage"
mkdir -p "$(dirname "$MAHJONG_POCKET_CONFIG")"
uv run --locked python deploy/pocket-id/configure.py --output "$MAHJONG_POCKET_CONFIG"
docker build -t "$MAHJONG_IMAGE" .
docker compose --env-file "$MAHJONG_POCKET_CONFIG/stage.env" \
  -p mahjong-pocket-stage -f deploy/pocket-id/compose.yaml up -d
```

用相同的 Compose 參數執行 `ps`。等 `identity` 顯示 healthy 後，執行首次設定並取得管理員登入連結。

```sh
uv run --locked python deploy/pocket-id/configure.py --output "$MAHJONG_POCKET_CONFIG" --bootstrap
docker compose --env-file "$MAHJONG_POCKET_CONFIG/stage.env" \
  -p mahjong-pocket-stage -f deploy/pocket-id/compose.yaml \
  exec identity /app/pocket-id one-time-access-token owner
```

在瀏覽器開啟完整的一次性連結，為 `owner` 建立 Passkey。連結和設定檔都應私下保管。
若首次設定只完成一部分，保留現有管理員，到管理介面檢查 OIDC client 與 secret 再完成設定。

- 帳號管理：<http://localhost:18081>
- 測試牌桌：<http://localhost:18080>

埠衝突時可在初始化加上 `--table-port` 和 `--identity-port`，之後一律使用同一份
`stage.env`。本機設定的 cookie 允許使用 HTTP，**僅適用 localhost**，不可轉發到外網或區域網路。
停止測試時用原本的 Compose 參數執行 `down`，保留資料卷。

## 邀請朋友與恢復帳號

1. 在帳號管理頁開啟 Users → Add User → Create Signup Token。
2. 每人建立一條連結，使用次數設為 **1**，並設定期限。正式邀請從正式 HTTPS 管理頁建立。
3. 請朋友在瀏覽器開啟連結，選擇帳號名稱並建立 Passkey。已使用或過期的連結會失效，
   也可在 Active Signup Tokens 主動撤銷。
4. 朋友遺失所有 Passkey 時，先確認本人，再替**原帳號**建立 Login Code，讓他重新註冊
   Passkey。用原帳號才會保留原本的玩家 ID、座位與牌譜關聯。

牌桌的登出只會撤銷目前的牌桌 session。共用裝置也要從 Pocket ID 帳號頁登出。
Redis 的登入 session 只存在記憶體，重啟後使用者需重新登入。帳號與牌譜各有持久化資料卷。

## Windows 與 Tailscale Funnel 範例

以下範例使用 Windows 的 Docker Desktop Linux 容器與 PowerShell。Funnel 在外側提供 HTTPS，
將帳號的 8443 埠轉至主機 loopback 的 18085，將牌桌的 443 埠轉至 18084。
`funnel.yaml` 只設定本機服務，開放對外連線需要另外執行 Funnel 命令。
[官方 Funnel 指令](https://tailscale.com/docs/reference/tailscale-cli/funnel)

在專案目錄執行 `uv sync --locked`。先備妥對應版本的牌桌映像、專案外的私有設定父目錄，
以及自己的 HTTPS `.ts.net` 網址。把下列變數改成實際值，設定目錄本身須是新目錄。

```powershell
$env:MAHJONG_IMAGE = 'mahjong16:<reviewed-release>'
$env:MAHJONG_POCKET_CONFIG = '<deploy-root>\pocket-private'
$origin = 'https://<host>.<tailnet>.ts.net'
uv run --locked python deploy/pocket-id/configure.py --output $env:MAHJONG_POCKET_CONFIG --url $origin --table-port 18084 --identity-port 18085
docker compose --env-file "$env:MAHJONG_POCKET_CONFIG\stage.env" -p mahjong16-pocket -f deploy/pocket-id/compose.yaml -f deploy/pocket-id/funnel.yaml up -d --no-build
```

等 `identity` 為 healthy，在 loopback 完成首次設定，再開通帳號入口。

```powershell
uv run --locked python deploy/pocket-id/configure.py --output $env:MAHJONG_POCKET_CONFIG --url $origin --bootstrap-port 18085 --bootstrap
$tailscale = 'C:\Program Files\Tailscale\tailscale.exe'
& $tailscale funnel --bg --https=8443 http://127.0.0.1:18085
```

用同一組 Compose 參數執行 `exec identity /app/pocket-id one-time-access-token owner`，
在正式 HTTPS 網域為管理員建立 Passkey。WebAuthn 綁定網域，localhost 的 Passkey 不會移轉。
既有部署應沿用私有設定與帳號資料卷，首次設定僅供新部署。

### 切換牌桌與回復入口

- 全新牌桌可使用這個 Compose project 自己的牌譜卷。接回既有牌譜時，先備份並停止舊
  牌桌的 `web`，再設定 `MAHJONG_RECORDS_VOLUME` 為既有卷名稱，在同一個 Pocket ID project
  使用 `compose.yaml`、`funnel.yaml`、`production.yaml` 重建 `web`。確認新 `web` 掛載正確。
- 確認 Caddy 的本機入口後，用 `& $tailscale funnel --bg --https=443 http://127.0.0.1:18084`
  對外提供牌桌。確認兩個 HTTPS 網址、登入與重連都正常，再分享給朋友。
- 要回復時，先停新牌桌的 `web`，再啟動保留的原部署並把 Funnel 指回舊埠。採用
  舊 Authelia 共用帳密者，見 [Authelia 切換與回復](gateway.md#切換與回復入口)。
  同一牌譜卷只能由一個 `web` 寫入。保留新帳號卷、私有設定和金鑰，勿用 `down -v`。

升級舊測試設定時，先備份並核對 `stage.env` 的 `MAHJONG_IDENTITY_ISSUER` 是否與
`pocket.env` 的 `APP_URL` 相同。早期未使用 Redis 或未啟用逐請求 CSRF cookie 的
`proxy.cfg`，用 [設定產生器](../deploy/pocket-id/configure.py) 核對工作階段、token refresh
和 CSRF 欄位，保留原 client/cookie secret 和 encryption key。套用後使用者應重新登入。

## 備份與還原

[牌譜的 SQLite 備份](docker.md#備份與還原)也包含帳號與玩家 ID 的對照。備份前核對
現行 `web` 掛載的牌譜卷。備份與複製都沿用該部署的 Compose 參數和環境設定。
Pocket ID 的帳號、Passkey 登錄資料和私有設定另行備份。Windows 可用
[帳號備份腳本](../deploy/windows/backup-identity.ps1)，它呼叫
[SQLite 備份工具](../deploy/pocket-id/backup.py)，將帳號資料庫、上傳檔案和私有設定打包。
ZIP 含 encryption key 等機密，未另行加密。限制讀取權限，並另存加密的異機副本。

要接到既有的 [牌譜備份排程](../deploy/windows/install-backup.ps1)，將帳號備份腳本放在
`<deploy-root>\backup-identity.ps1`，把 Python 工具放在
`<deploy-root>\backup-source\pocket-backup.py`，沿用服務使用者與 SYSTEM 的專用 ACL。
在排程執行的 `<deploy-root>\backup-hands.ps1` 末尾加入以下命令。

```powershell
& ([scriptblock]::Create([IO.File]::ReadAllText('<deploy-root>\backup-identity.ps1'))) `
    -DeployRoot '<deploy-root>'
```

如果用了不同的容器名稱，核對牌譜排程的 `-Container` 及帳號腳本的 `-Container`、
`-WebContainer`。重裝排程後要加回帳號備份呼叫。驗證 `LastTaskResult=0`，
並確認日誌都有 `Verified backup` 與 `Verified identity backup`。備份同時修改頭像時，
頭像可能與 SQLite 快照不同步。

還原先用隔離網路和新資料卷，檢查 ZIP CRC、檔案路徑與 SQLite integrity。
將 `identity/` 還原至 `/app/data`，讓容器 UID/GID 10001 可存取，
`config/` 還原到專用私有目錄。用同版本 Pocket ID 映像、原 encryption key 和 `APP_URL`
啟動，核對原帳號、WebAuthn 資料和 OIDC client，再實際登入。正式還原先停止寫入，
保留現有資料卷作為回復點，再切到驗證過的新卷。變更 WebAuthn 網域可能讓原 Passkey 無法使用。

## 驗收

```sh
uv run --locked pytest -q tests/web/test_pocket_id_configuration.py tests/web/test_gateway_configuration.py
MAHJONG_IMAGE=mahjong16:pocket-stage uv run --locked python tests/web/pocket_id_smoke.py
```

整合測試使用獨立設定和資料卷，驗證邀請、OIDC、故障時拒絕存取及隔離還原。上線前另用實際
瀏覽器和裝置測試 Passkey 建立、登入、取消、跨裝置登入和帳號恢復。曾在 Windows 驗證
HTTPS、管理員 Passkey 註冊和隔離還原後的 session 登入。iPhone、還原後的實機 Passkey
及切回 Authelia 仍需實際演練。

延伸說明見 [Pocket ID 帳號與邀請](https://pocket-id.org/docs/setup/user-management)、
[登入方法](https://pocket-id.org/docs/guides/sign-in-methods)與
[OAuth2 Proxy OIDC 設定](https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/openid_connect/)。
