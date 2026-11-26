# Authelia 共用帳密閘道

這是使用 Caddy 與 Authelia 的進階入口，也可作為 [Pocket ID](pocket-id.md) 的既有回復入口。
基本自架見 [Docker Compose](docker.md)。

只有 Caddy 的入口映射到主機 loopback。Caddy 會在登入後提供牌桌的後端憑證，
牌桌仍會檢查座位與操作權限。Authelia 驗證失敗或服務故障時，閘道拒絕存取。
請保護私有設定中的後端通行碼和 Authelia 金鑰。

## 隔離測試

先啟動 Docker 引擎，在專案目錄執行 `uv sync --locked`。測試使用獨立的設定與資料卷。
預先準備 [Compose 指定的 Caddy 映像](../deploy/gateway/compose.yaml)，並用 `MAHJONG_IMAGE`
指定本機已建置的牌桌映像。

```sh
uv run --locked python tests/web/gateway_smoke.py
uv run --locked python tests/web/gateway_smoke.py --funnel
```

測試涵蓋匿名存取、偽造標頭、登入、基本房間操作與驗證故障。第一條用短期測試憑證，
第二條測試 Funnel 的本機 HTTP 入口。正式 HTTPS 請驗證有效的憑證。
Windows 的測試目錄位於 `MAHJONG_DEPLOY_ROOT`，預設為 `C:\ProgramData\mahjong16`，
並沿用服務使用者與 SYSTEM 的專用 ACL。

## Windows 與 Tailscale Funnel 範例

以下用 PowerShell 操作。在專案目錄執行 `uv sync --locked`，備妥 Linux 容器模式的 Docker 引擎、牌桌映像和專案外的
私有設定父目錄。將網址與路徑改為實際值，設定目錄須尚未建立。

```powershell
$env:MAHJONG_IMAGE = 'mahjong16:<reviewed-release>'
$env:MAHJONG_GATEWAY_HOST = '<host>.<tailnet>.ts.net'
$env:MAHJONG_GATEWAY_CONFIG = '<deploy-root>\gateway-private'
$env:MAHJONG_GATEWAY_PORT = '8003'
uv run --locked python deploy/gateway/configure.py --output $env:MAHJONG_GATEWAY_CONFIG --url "https://$env:MAHJONG_GATEWAY_HOST" --user friend
docker compose -p mahjong16-gateway-ready -f deploy/gateway/compose.yaml -f deploy/gateway/funnel.yaml up -d --no-build
```

在本機讀取 `login.txt`，私下交付帳密。初始化會建立私有設定並拒絕覆寫。
原生 Linux 須確認容器 UID 10001 可讀取掛載的私有設定。此範例的 `funnel.yaml` 只在
loopback 開放 HTTP，外部 TLS 由 Funnel 提供。帳號輸錯三次會短暫封鎖帳號，封鎖
以帳號計算。Authelia 重啟後現有 session 會失效。
[Authelia 帳號封鎖](https://www.authelia.com/configuration/security/regulation/)

## 切換與回復入口

1. 切換前記下目前的映像、Compose project、牌譜卷和 Funnel 目標。核對現行 `web` 的
   牌譜卷，用該部署的 Compose 參數執行[備份與複製](docker.md#備份與還原)，
   並保留原部署和私有設定作為回復點。
2. 若要接回既有牌譜，先停止舊牌桌的 `web`，將 `MAHJONG_RECORDS_VOLUME` 設成既有卷名稱，
   再用同一個新 project 加上 `deploy/gateway/production.yaml` 重建。核對實際掛載的卷。
   同一牌譜卷只能由一個 `web` 寫入，勿執行 `down -v`。
3. 確認本機 HTTP 入口後，把 Funnel 的 HTTPS 443 指向 `http://127.0.0.1:8003`。
   在瀏覽器驗證登入、重連和多人開房，再交付使用。
4. 要回復舊入口時，先停止現用牌桌的 `web`，再啟動保留的原 `web`、閘道與驗證服務，
   將 Funnel 指回原埠。如從 Pocket ID 回復到共用帳密，保留 Pocket ID 帳號卷、私有設定
   和金鑰。驗證故障時維持登入檢查。

對局能否續接取決於引擎版本和牌譜格式。詳見 [網頁續局與重播](hand-recording.md#網頁續局與重播)。
