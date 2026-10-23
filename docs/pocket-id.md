# 朋友邀請、Passkey 與正式部署

Pocket ID 管理每位朋友的帳號；正式入口已於 2026-10-23 從 Authelia 切換。
本文件同時保留獨立 localhost 驗證流程，兩者使用不同設定與資料卷，不能互換。
macOS 與 Windows Docker Desktop 已完成容器測試；Windows 設定在寫入憑證前
限制 ACL 為服務使用者與 SYSTEM。原生 Linux 的 bind mount 權限仍須另外驗證，
不能以改成公開可讀解決 UID 不同的問題。

正式牌桌為 `https://desktop-388mjbr.tail62f6aa.ts.net/`，帳號服務在相同網域的
`:8443`。只有收到有效註冊邀請的人能建立帳號；舊共用帳密不再用於此入口。

## 架構與責任

```text
localhost:18081 → Caddy → Pocket ID → 獨立 identity-data SQLite
localhost:18080 → Caddy → OAuth2 Proxy／Redis → Pocket ID token 檢查 → 測試牌桌
```

Pocket ID 管理帳號、邀請、Passkey 與恢復；OAuth2 Proxy 是 OIDC client。
驗證成功後 Caddy 才把請求與私有後端憑證轉交牌桌。牌桌與驗證服務沒有主機映射埠，
兩者分別使用 internal network；只有 Caddy 同時連入兩個網路。
第三方映像固定版本與 digest；容器非 root、唯讀 rootfs、限制資源及日誌大小。
Redis 只在驗證內網保存可撤銷的 session，不映射主機埠，也不寫入磁碟。
它停止／重建後須重新登入，但不會刪除 Pocket ID 帳號、Passkey 或牌譜。

此階段刻意保留牌桌現有的座位與操作授權，不新增麻將引擎的帳號邏輯。
Caddy 先移除外部 `X-Qinghe-Subject`，再將驗證成功的 subject 傳給牌桌；
牌桌須同時驗證私有閘道憑證，且明確啟用 `--trusted-identity-issuer`。
`HandStore.account_players` 將 issuer/subject 對應到固定玩家 UUID，
用於初始座位、中途接管與逐步決策的 player_id。原始登入識別不放進牌譜或玩家 snapshot。
同帳號多裝置會找回同一個房間與座位，不能同時佔據多個座位；
同瀏覽器換帳號會依新帳號處理，不沿用前一人的匿名 Cookie。
這提供後續戰績統計的識別基礎，尚未新增戰績頁或將歷史匿名牌譜猜配成帳號。

## 啟動

先依 [Docker 文件](docker.md) 啟動 Docker 引擎、同步鎖定環境。
使用新的專用目錄；初始化拒絕覆寫，也拒絕將憑證存入 repository。

```bash
source .venv/bin/activate
export MAHJONG_IMAGE=mahjong16:pocket-stage
export MAHJONG_POCKET_CONFIG="$HOME/.config/mahjong16/pocket-stage"
mkdir -p "$(dirname "$MAHJONG_POCKET_CONFIG")"
python deploy/pocket-id/configure.py --output "$MAHJONG_POCKET_CONFIG"
docker build -t "$MAHJONG_IMAGE" .
docker compose --env-file "$MAHJONG_POCKET_CONFIG/stage.env" \
  -p mahjong-pocket-stage -f deploy/pocket-id/compose.yaml up -d
```

等待 identity healthy，再執行一次首次設定：

```bash
python deploy/pocket-id/configure.py --output "$MAHJONG_POCKET_CONFIG" --bootstrap
```

它使用 Pocket ID 官方 API 建立 `owner` 管理員與專用 OIDC client，啟用 PKCE，
callback 僅允許 `http://localhost:18080/oauth2/callback`。
首次設定之後 Pocket ID 會拒絕再次建立初始管理員；失敗時不要刪除已有帳號繞過限制。
若中途失敗，檢查管理介面中的 client／secret 完成設定；bootstrap 不是修復或重設工具。
此流程不會為人產生 Passkey；後續須由使用者在自己的瀏覽器完成。

取得第一個管理員的一次性登入連結：

```bash
docker compose --env-file "$MAHJONG_POCKET_CONFIG/stage.env" \
  -p mahjong-pocket-stage -f deploy/pocket-id/compose.yaml \
  exec identity /app/pocket-id one-time-access-token owner
```

只在自己的終端讀取連結，勿貼到聊天、Git、截圖或共用日誌。
開啟連結後替 `owner` 建立 Passkey；平常入口為：

- 帳號管理：<http://localhost:18081>
- 測試牌桌：<http://localhost:18080>

首次測試請將完整一次性連結貼入 Chrome 或 Safari，而非直接開一般登入入口。
一般登入頁的「驗證」要求已有 Passkey；一次性登入成功後應到
`/signup/add-passkey` 的「設定您的密碼金鑰」，再按「新增密碼金鑰」建立。
若頁面已是新增密鑰但系統仍表示沒有儲存的密鑰，先用另一個完整瀏覽器對照；
不能只憑這個訊息判定帳號沒建立或把註冊改成登入，也不要重建帳號。
不同瀏覽器的登入 Cookie 不共用；切換瀏覽器時需新的未用過的一次性連結。
建立／儲存 Passkey 的裝置提示須由使用者親自完成。
Pocket ID 此版本也提供「暫時跳過」，但略過後仍須另行建立長期登入方式。

2026-10-23 本機驗收：使用者在 Codex／ChatGPT 內建瀏覽器到達新增密鑰頁，
裝置提示卻未完成建立；改以 Chrome 開新的一次性連結後，已由使用者親自完成
Passkey 儲存並進入「我的帳號」。固定版本的該頁確實呼叫 `startRegistration`，
不是 `startAuthentication`。此結果不證明所有內建瀏覽器都不支援，也尚未確認
底層瀏覽器／密鑰供應器的失敗原因；首次設定先使用這次驗收成功的 Chrome。

`--table-port` 與 `--identity-port` 可在初始化時指定不同的本機埠。
必須使用同一份 `stage.env` 啟動，不能只改 Docker port 而留下舊的 OIDC callback。
切勿將測試 Passkey 當成正式帳號憑證：正式 HTTPS 網域需要重新設定與驗收。

## 朋友加入與恢復

設定由環境固定為 `ALLOW_USER_SIGNUPS=withToken`，不開放公開註冊。
不要求 email、不啟用 SMTP；使用者驗證設為 required，允許同步 Passkey。

1. 管理員進入 Users → Add User → Create Signup Token。
2. 每位朋友建立一條連結，帳號建立數設為 **1**，設定期限，例如 24 小時。
3. 朋友開連結、自取 username／顯示名稱，再依 Pocket ID 畫面建立 Passkey。
4. 用過、過期或從 Active Signup Tokens 撤銷的連結不能再建立帳號。
5. 遺失全部 Passkey 時，先在既有私訊管道確認本人，再為**原帳號**建立 Login Code；
   不重發註冊連結建立第二個帳號。

本機測試產生的 localhost 連結只能在本機使用；正式邀請須從正式 `:8443` 管理頁建立。
Pocket ID 的一次性登入可用於恢復，安全程度依賴你確認收件人及保護連結。
Passkey 不在手邊時，也可使用官方提供的另一裝置登入方式，實際支援須實機驗收。

## 已驗證的邊界與尚未完成的部分

```bash
source .venv/bin/activate
pytest -q tests/web/test_pocket_id_configuration.py tests/web/test_gateway_configuration.py
MAHJONG_IMAGE=mahjong16:pocket-stage python tests/web/pocket_id_smoke.py
```

smoke 使用隨機 project、全新憑證與兩個測試資料卷，結束只清除這個 project。
測試匿名／偽造憑證不能到達牌桌、沒有私有服務主機埠、首次 setup 不能重用、
沒有任何 Passkey 的帳號仍可取得新密鑰的註冊 challenge 與 localhost RP 設定、
邀請必填／一次性／過期／撤銷、恢復保留帳號 ID，以及兩個帳號經真實 OIDC／PKCE／
同意畫面／CSRF 驗證登入牌桌。驗證代理停止時，即使帶既有 cookie 仍被拒絕。
此測試透過官方邀請與一次性登入 session 測試 OIDC，不模擬或冒充真人 Passkey。
另外會停止可丟棄測試專案，備份帳號／牌譜資料卷與私有設定，再還原到另一個
全新專案，確認帳號、加密的 OIDC client secret、牌譜與玩家 ID 能延續。
這是停機冷備份演練，與下節正式主機的 SQLite 線上備份不同；測試不操作現有使用者資料卷。

尚須在瀏覽器及實機驗收 Passkey 建立、登入、取消、跨裝置與恢復。
HTTP localhost 是瀏覽器允許 WebAuthn 的開發例外，且此處代理 cookie 為非 Secure；
**不能將 localhost 設定接到 Funnel、反向轉接至外網或改綁 LAN**。
正式部署另使用下節的 HTTPS 設定與 `funnel.yaml`。
正式部署必須使用固定 HTTPS 網域、Secure cookies 與驗證過的 issuer／callback。
Pocket ID cookie 是服務本身的 session；牌桌的 session 改由 Redis 保存。
`/oauth2/sign_out` 刪除對應的伺服器端 session，複製的原 cookie 也無法重用，
並停在 `/oauth2/signed-out`，避免立刻重新登入。這只登出該份牌桌 session；
不會登出其他裝置或 Pocket ID 本身，共用裝置仍須另行登出帳號服務。

代理要求 `offline_access`，以 `cookie_refresh=1s` 透過官方 refresh token 流程
重新確認帳號資格，停用後於下一次刷新阻擋；實測使用 3 秒期限驗證，
不宣稱零延遲撤銷，也不會收回已在處理中的 HTTP 請求。
只查 userinfo 不足以偵測此版本的停用帳號，因此不能移除 refresh 檢查。
Caddy 仍逐次呼叫 userinfo 驗證 access token，讓 Pocket ID 故障時阻擋牌桌請求。
access token 只在驗證內網轉交，送至牌桌前移除，也不透過 `/oauth2/*` 回傳給瀏覽器。

cookie／Redis TTL 設定為 12 小時；成功刷新會續延伺服器端 TTL，並非絕對的
12 小時登入上限，仍受 IdP/token 政策限制。未提供 30 天記住裝置產品流程。
到期檢查只在可丟棄設定縮為 5 秒，未真的等待 12 小時。

可信 OIDC subject → 固定 player ID → 座位／牌譜的映射已在本機實作與測試；
測試也涵蓋同一 HTTP keep-alive 連線換帳號，避免快取沿用前一人的身分。
同一 issuer/subject 的玩家 ID 跨房間、牌局與服務重啟保留，
但進行中的房間仍只在記憶體，重啟後不會恢復牌局。
account_players 是現有 SQLite 的相容新增表，不改 hands 表或舊 JSON，保留 user_version=1。
映射隨原有 SQLite backup 保存；Pocket ID 帳號資料卷與 encryption key
已一起完成可丟棄帳號的冷備份還原演練。Windows Docker、正式 HTTPS 與管理員
Passkey 註冊已驗證；正式帳號備份也已還原到隔離容器，核對帳號與 WebAuthn 資料，
並完成還原後 session 登入。這不等於已實測真人用還原的 Passkey 再次完成裝置驗證。
iPhone、跨裝置金鑰登入與正式回復到 Authelia 的切換演練尚未完成。

先前產生的本機設定不會被初始化程式覆寫。更新時須在私有 `stage.env` 補上
`MAHJONG_IDENTITY_ISSUER`，值須與 `pocket.env` 的 APP_URL 完全相同，
並使用新映像重建測試 web/gateway；不要重建帳號或刪除 identity-data。
舊 `proxy.cfg` 也須保留原 client/cookie secret，補上 `session_store_type="redis"`、
`redis_connection_url="redis://sessions:6379/0"`、`pass_access_token=true`，
scope 加上 `offline_access`，並將 `cookie_refresh` 改成 `"1s"`。
啟動 sessions，再重建 proxy/gateway；舊 Cookie 會失效，須重新登入並同意新增 scope。
身份設計與回復邊界見 [ADR](adr/0001-account-player-identity.md)。

停止此測試部署時，沿用相同的 `--env-file`、project 與 Compose 檔執行 `down`，
不加 `-v` 可保留測試帳號與資料。不要對正式專案使用此文件的清理命令。

## Windows 正式 HTTPS 部署

`funnel.yaml` 使用同一組服務與獨立的 Caddy 入口設定；只有 gateway 綁定主機
loopback，牌桌、Pocket ID、代理與 Redis 都沒有公開主機埠。
Funnel 終止 TLS：443 轉至 18084，8443 轉至 18085。固定 HTTPS issuer 與 callback，
牌桌 Cookie 使用 `__Host-` 名稱、Secure、HttpOnly、SameSite=Lax。
帳號服務有獨立 origin，不能把 Pocket ID 塞進 `/auth` 子路徑。

首次部署先在未公開的 loopback 建置與完成 bootstrap，再啟用帳號服務 Funnel。
以下初始化只適用**全新**目錄；現有部署不能重跑來覆寫帳號與金鑰。

```powershell
$env:MAHJONG_IMAGE = 'mahjong16:<reviewed-release>'
$env:MAHJONG_POCKET_CONFIG = 'C:\ProgramData\Qinghe\pocket-private'
uv run --locked python deploy/pocket-id/configure.py --output $env:MAHJONG_POCKET_CONFIG --url https://desktop-388mjbr.tail62f6aa.ts.net --table-port 18084 --identity-port 18085
docker compose --env-file "$env:MAHJONG_POCKET_CONFIG\stage.env" -p mahjong16-pocket -f deploy/pocket-id/compose.yaml -f deploy/pocket-id/funnel.yaml up -d --no-build --pull never
uv run --locked python deploy/pocket-id/configure.py --output $env:MAHJONG_POCKET_CONFIG --url https://desktop-388mjbr.tail62f6aa.ts.net --bootstrap-port 18085 --bootstrap
& 'C:\Program Files\Tailscale\tailscale.exe' funnel --bg --https=8443 http://127.0.0.1:18085
```

讀取一次性管理員連結並在正式 HTTPS 建立 Passkey。localhost 的 Passkey 不能
當成正式網域的註冊；不要刪除本機或正式帳號來嘗試繞過裝置問題。
bootstrap 先確認本機 client 設定可讀，部分失敗時保留既有管理員，查明後完成設定。

切換前備份舊牌譜、停止舊 web writer，再加入 `production.yaml`，設定
`MAHJONG_RECORDS_VOLUME=mahjong16-docker-617094b_hand-records`，用原 project
加上三個 Compose 檔重建 web。核對新 web 的實際 mount 後，才將 Funnel443 切至
`http://127.0.0.1:18084`。不能同時啟動新舊 web 寫入同一資料卷。
重啟清除記憶體房間，不清除已保存牌譜；`account_players` 隨牌譜 SQLite 保存。

回復時先停新 web，再啟動保留的 `mahjong16-gateway-ready` 舊 web/gateway/auth，
把 Funnel443 指回 `http://127.0.0.1:8003`。保留新 identity-data、私有設定及金鑰，
不執行 `down -v`。回復採舊共用帳密流程，須由管理員明確決定，不能因登入失敗
自動放行。Docker Desktop 仍需 Windows 使用者登入並啟動引擎；此部署沒有改成
開機免登入服務，也沒有新增 GitHub 自動部署。

## 正式帳號備份與還原

牌譜沿用 [Windows SQLite 備份](docker.md#windows-主機端備份)。帳號另由
`deploy/windows/backup-identity.ps1` 呼叫 `deploy/pocket-id/backup.py`，使用 SQLite
backup API 取得一致快照，再連同 uploads 與八份私有設定封裝 ZIP；包括 encryption key，
不包含一次性 owner 登入連結。先寫 `.partial`，驗證完整性與 ZIP CRC 後才改名。
uploads 不和 SQLite 共用交易，備份時修改頭像可能造成頭像版本不一致。

將兩個檔案分別安裝在 `C:\ProgramData\Qinghe\backup-identity.ps1` 與
`C:\ProgramData\Qinghe\backup-source\pocket-backup.py`，檔案及備份目錄維持
服務使用者與 SYSTEM 的專用 ACL。在既有隱藏的每小時備份腳本末尾呼叫：

```powershell
& ([scriptblock]::Create([IO.File]::ReadAllText('C:\ProgramData\Qinghe\backup-identity.ps1')))
```

不重新安裝／改動現有 wscript 隱藏 launcher；牌譜備份的 Container 改為
`mahjong16-pocket-web-1`。驗證排程 `LastTaskResult=0`，日誌須同時出現兩種
Verified backup 訊息。帳號 ZIP 保留 30 天，硬上限 744 份；牌譜保留原有的
48 小時逐時與 30 天每日策略。只清理精確命名的備份，不處理連結或 junction。

ZIP 含機密且未另加密，不能提供公開下載、提交 Git 或傳入聊天。這是同機備份，
不能防止整台主機／硬碟損毀；需要異機備份時另行設置加密與金鑰保管。

還原先在隔離 network 與全新資料卷演練：檢查 ZIP CRC、路徑、SQLite integrity，
將 `identity/` 還原至 `/app/data`，`config/` 還原至專用私有目錄；容器檔案歸
UID/GID 10001。以相同 pinned Pocket ID 映像、原 encryption key 與 APP_URL 啟動，
核對原帳號／WebAuthn 資料與 OIDC client，再測試登入。不要覆寫正在使用的卷。
正式還原須停 identity 寫入、保留目前卷的回復點，再切到驗證過的還原卷。
若更改 APP_URL／RP 網域，不能保證原 Passkey 繼續可用。

## 官方依據

- [Pocket ID 帳號與邀請](https://pocket-id.org/docs/setup/user-management)
- [Pocket ID 登入方法](https://pocket-id.org/docs/guides/sign-in-methods)
- [Pocket ID 驗證代理整合](https://pocket-id.org/docs/guides/proxy-services)
- [Pocket ID 環境變數](https://pocket-id.org/docs/configuration/environment-variables)
- [OAuth2 Proxy OIDC](https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/openid_connect/)
- [OAuth2 Proxy session 儲存](https://oauth2-proxy.github.io/oauth2-proxy/configuration/session_storage/)
- [OpenID Connect 固定身分識別](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability)
