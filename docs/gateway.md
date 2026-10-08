# 前置驗證部署

`deploy/gateway/` 是獨立測試部署，尚未接入正式 Funnel。
本次支援範圍為 Mac／Windows Docker Desktop，正式目標是 Windows。
原生 Linux Docker 尚未驗證；主機產生的 0600 設定通常不能由容器 UID 10001
直接讀取，須另外設計檔案擁有者／掛載權限，不能直接沿用此流程。
不要以此 Compose project 取代正式 project，也不要將正式牌譜資料卷掛進測試。
測試期間朋友仍使用目前的公開版；其牌局不會被重啟。

入口使用 Caddy，驗證使用 Authelia；映像以 digest 固定版本。
只有 Caddy 的測試 TLS 埠映射至主機 loopback。Authelia 與牌桌各自使用
Docker internal network，只有 Caddy 同時連入兩個網路，兩者不直接互連。
未通過驗證的請求不轉送牌桌；驗證服務故障時回傳錯誤，不直接放行。
Caddy 管理 API 關閉；服務以 UID 10001 運行，唯讀程式目錄並限制資源。
短期初始化容器只以 root 調整三個專用資料卷的擁有者，無網路、僅有 CHOWN 能力。
官方 Caddy binary 自帶 NET_BIND_SERVICE file capability，因此執行它需要保留此能力。

驗證通過後，Caddy 覆寫後端 Authorization，提供牌桌原本要求的憑證。
因此朋友不需再登入牌桌一次，原本的後端通行碼檢查也保持啟用。
閘道會取得這份後端憑證，故閘道失守後仍可能存取牌桌；這不是完全隔離。
前置驗證不取代牌桌 API 本身的座位及操作權限檢查。

## 可重跑的測試

```bash
.venv/bin/python tests/web/gateway_smoke.py
.venv/bin/python tests/web/gateway_smoke.py --funnel
```

Windows 使用該主機的 Python 路徑執行相同檔案，Docker CLI 必須在 PATH，
並沿用 `docs/docker.md` 的專用 DOCKER_CONFIG 與 Docker Desktop engine。
Windows 測試目錄位於已限制為本人與 SYSTEM 的 `C:\ProgramData\Qinghe` 下，
繼承該目錄 ACL，讓 Docker Desktop 的主機服務可讀取測試憑證。

測試生成隨機帳密、Argon2id 密碼雜湊與獨立私有設定，使用唯一 project 名稱，
不使用正式通行碼或資料庫。測試結束移除該 project 的容器、網路、資料卷與臨時憑證。
失敗時保留的診斷輸出也僅屬於測試帳號，不是正式憑證。

測試覆蓋未登入阻擋、偽造標頭阻擋、驗證服務故障時拒絕存取、
登入及記住裝置的 cookie、靜態資源、建立／開始／離開房間。
以後端日誌確認被拒絕的特定探針沒有抵達牌桌，並核對後端及驗證服務沒有主機映射埠。
TLS 憑證僅用於測試；探針只對這個短期 listener 略過憑證驗證，正式 HTTPS 不應略過。
2026-10-08 已在 Mac Docker Desktop 與 `DESKTOP-388MJBR` Docker Desktop 跑過上述測試。

## Funnel 入口與私有帳號

`funnel.yaml` 將 Caddy 換成主機 loopback 的 HTTP 入口，公開 HTTPS 由 Funnel 提供。
只接受設定的 hostname；對驗證及牌桌明確指定外部 scheme 為 HTTPS，
避免登入跳轉及 Secure cookie 因內部 HTTP 失效。它不會自行啟用 Funnel。
外部提供的 X-Forwarded-For 與 X-Real-IP 被移除，不信任偽造的來源 IP。
目前使用 Authelia 預設的帳號封鎖：2 分鐘內 3 次失敗，暫停 5 分鐘；
此措施不是按 IP 的流量限制，攻擊者也可能藉輸錯密碼暫時封鎖朋友的帳號。
依據：[Authelia regulation](https://www.authelia.com/configuration/security/regulation/)。

使用 Windows 既有的私有 DOCKER_CONFIG 與 Docker engine，建立新設定：

```powershell
python deploy/gateway/configure.py --output C:\ProgramData\Qinghe\gateway-private --url https://desktop-388mjbr.tail62f6aa.ts.net --user friend
```

產生器拒絕 repository 內的目錄及既有輸出目錄，避免覆寫帳號、session secret
或 SQLite encryption key。Windows 在寫入憑證前設定本人與 SYSTEM 的專用 ACL；
Linux/macOS 使用目錄 0700、檔案 0600。
Authelia 自行產生隨機密碼與 Argon2id hash，不將密碼放進指令參數或終端輸出。
帳密只寫入 `login.txt`，朋友密碼應私下提供；`gateway.env` 與後端通行碼也不能提交 Git。
users.yml 使用佔位 email，目前停用密碼重設、沒有寄信功能。

```powershell
$env:MAHJONG_GATEWAY_HOST = 'desktop-388mjbr.tail62f6aa.ts.net'
$env:MAHJONG_GATEWAY_CONFIG = 'C:\ProgramData\Qinghe\gateway-private'
$env:MAHJONG_GATEWAY_PORT = '8003'
docker compose -p mahjong16-gateway-ready -f deploy/gateway/compose.yaml -f deploy/gateway/funnel.yaml up -d
```

以上仍使用獨立牌譜卷，不更改正式服務。Caddy/Authelia/牌桌會自動重啟，
Docker 日誌每服務保留最多 3 個 10MB 檔案。
2026-10-08 已在 Mac 測試 TLS 與 Funnel HTTP 兩種入口，在 Windows 測試 Funnel HTTP 入口。
兩者均驗證未授權帳號不能接觸牌桌，以及被封鎖帳號即使用正確密碼仍被拒絕。

## 正式切換前還需要完成

- 核對正式帳號與私有設定，確認未使用測試帳密。
- 驗證正式 Funnel HTTPS 與瀏覽器登入；目前不宣稱已完成按朋友 IP 的限流。
- 測試瀏覽器登入、重連與多人操作，備份資料並保留回復入口。
- 說明重啟造成記憶體牌局清除，再取得正式切換同意。

取得切換同意並完成備份後，先停止舊 web 容器，才可加入 `production.yaml`：
將 MAHJONG_RECORDS_VOLUME 設為既有 `mahjong16-docker-617094b_hand-records`，
用相同 project 加上三個檔案 `compose.yaml`、`funnel.yaml`、`production.yaml` 重建。
此 overlay 只換成既有 external 牌譜卷，不刪除它；不可同時運行兩個寫入該卷的牌桌。
既有備份工作仍讀相同卷，不須換資料來源。不要對這個正式 project 使用 `down -v`。
確認本機入口後，才把 Funnel 的 443 入口切至 `http://127.0.0.1:8003`。
回復時先停止新 web，恢復舊容器並將 Funnel 指回 8002，保留原映像與資料卷。
正式換回舊入口會恢復共用通行碼流程；不要在失敗時自動略過登入檢查。

目前登入有效期為 12 小時，勾選記住裝置為 7 天；這些僅是測試設定。
Authelia session 使用記憶體，驗證服務重啟會要求重新登入。
此階段沒有新增 Redis、郵件服務、自助註冊、邀請連結或自動部署。

依據：[Authelia 的 Caddy 整合](https://www.authelia.com/integration/proxies/caddy/)。
