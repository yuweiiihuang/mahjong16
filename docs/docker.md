# Docker 牌桌

以通行碼版本 `617094b` 為第一個容器基準；使用 Docker Desktop 的 Linux containers。
Mac 本地驗證後，Windows 再部署指定版本。此階段手動建置與部署，尚未接 GitHub
Actions、GHCR、自動更新或獨立入口驗證。登入仍由牌桌程式處理。

2026-10-07 Windows 首次置中更新映像為 `mahjong16:617094b-centered`，在 `617094b`
基準上移除鏡頭的水平偏移。Funnel 指向 8002；舊 Python 服務已停止且排程已停用。

## Mac 驗證

通行碼放在專案外，至少 16 字元，檔案僅允許本人讀取。以下建立獨立測試通行碼：

```bash
mkdir -p "$HOME/.config/mahjong16"
chmod 700 "$HOME/.config/mahjong16"
uv run --locked python -c 'import secrets; from pathlib import Path; p=Path.home()/".config/mahjong16/docker-test-password.txt"; p.write_text(secrets.token_urlsafe(32)); p.chmod(0o600)'
export MAHJONG_PASSWORD_FILE="$HOME/.config/mahjong16/docker-test-password.txt"
export MAHJONG_PORT=8002
export MAHJONG_IMAGE="mahjong16:$(git rev-parse --short HEAD)"
docker compose build
docker compose up -d --no-build --pull never --wait
uv run --locked python tests/web/container_smoke.py --password-file "$MAHJONG_PASSWORD_FILE"
```

開啟 `http://127.0.0.1:8002/`，輸入測試通行碼，確認登入、牌桌比例與操作。
測試結束執行 `docker compose down`，不影響其他連接埠的牌桌。
測試通行碼檔案已存在時不要重跑生成步驟，以免覆寫；需更換時在停桌後另行生成。

## Windows 部署與回復

先安裝 Docker Desktop、完成 WSL 2／Linux containers 設定並啟動 Docker 引擎。
在正式切換前，以不同連接埠測試，保留 `Mahjong16-Web` 舊服務。
既有正式通行碼仍放在 `C:\ProgramData\Qinghe\access-password.txt`，不複製到 Git。

在所需 Git 版本的專案目錄，用 PowerShell 執行：

```powershell
$env:MAHJONG_PASSWORD_FILE = 'C:\ProgramData\Qinghe\access-password.txt'
$env:MAHJONG_PORT = '8002'
$env:MAHJONG_IMAGE = 'mahjong16:' + (git rev-parse --short HEAD)
docker compose build
docker compose up -d --no-build --pull never --wait
uv run --locked python tests/web/container_smoke.py --password-file $env:MAHJONG_PASSWORD_FILE
```

首次啟動 Docker Desktop 必須從 Windows 桌面完成條款確認；若遠端啟動後沒有視窗，
先關閉該次 Docker 程序，再由桌面開啟。登入後等待 Docker 引擎就緒，再執行建置。

透過 SSH 建置公開映像時，Windows 憑證庫可能回報
`A specified logon session does not exist`。使用獨立的命令列配置，不修改桌面登入資料：

```powershell
$dockerRoot = "$env:LOCALAPPDATA\Programs\DockerDesktop"
$env:DOCKER_CONFIG = 'C:\ProgramData\Qinghe\docker-cli'
$env:DOCKER_HOST = 'npipe:////./pipe/dockerDesktopLinuxEngine'
New-Item -ItemType Directory -Force $env:DOCKER_CONFIG | Out-Null
$config = @{auths=@{'ghcr.io'=@{}; 'https://index.docker.io/v1/'=@{}}; cliPluginsExtraDirs=@("$dockerRoot\resources\cli-plugins")}
[IO.File]::WriteAllText("$env:DOCKER_CONFIG\config.json", ($config | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
& "$dockerRoot\resources\bin\docker.exe" compose build
```

公開 registry 的空白項目可避免 Docker 自動選用 Windows 憑證庫。
這份匿名配置只適用公開映像。需要私人 registry 時另行設置認證，
不要覆寫已有認證的配置。`C:\ProgramData\Qinghe` 必須維持服務帳號與 SYSTEM 的存取限制。

確認測試容器可用並同意切換至新牌桌後，將 Funnel 改指向 Docker 的 8002 埠。
舊服務繼續使用 8000，保留原本牌局供切回：

```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' funnel --bg http://127.0.0.1:8002
```

公開網址保持不變，也不公開主機的 8002 埠。舊服務已停止時，須先啟用並啟動排程、
確認 `http://127.0.0.1:8000/` 可用，再切回；重新啟動不會恢復先前牌局：

```powershell
Enable-ScheduledTask -TaskName Mahjong16-Web
Start-ScheduledTask -TaskName Mahjong16-Web
& 'C:\Program Files\Tailscale\tailscale.exe' funnel --bg http://127.0.0.1:8000
```

後續更新先記下目前 `MAHJONG_IMAGE`，再建置新版本。需回復時將該變數設成上一個
仍保留的映像標籤，再執行 `docker compose up -d --no-build --pull never --wait`。
不要刪除仍可能用到的舊映像，也不要在有人遊玩時換版。

## 邊界與維護

- 容器使用 UID 10001、唯讀檔案系統，移除 Linux capabilities，限制 CPU、記憶體與程序數。
- 對外埠只綁主機 `127.0.0.1`；透過 Funnel 提供 HTTPS，SSH 仍經 Tailscale 管理。
- Compose 只掛載通行碼檔案；不掛載整個專案、SSH 金鑰或 Docker socket。
- Mac Docker Desktop 已實測 `0600` 通行碼檔案可由容器 UID 10001 讀取；Windows
  已實測受限制 ACL 的通行碼檔案可正常登入。原生 Linux 的 bind mount 會保留主機 UID，須另行對齊檔案擁有者，
  不應將通行碼改成所有人可讀。此文件的部署目標是 Mac／Windows Docker Desktop。
- 映像依 `uv.lock` 安裝環境，建置內容由 `.dockerignore` 白名單限制。
- 健康檢查確認登入頁可讀，不建立牌局；登入與多人操作由 smoke check 驗證。
- `restart: unless-stopped` 需 Docker 引擎先運行；不代表 Windows 未登入就能自動啟動。
- 牌局仍在記憶體中，容器重啟／換版會清除牌局。健康檢查失敗也不會自行重啟容器。
- 日誌限制每檔 10 MB、保留三檔。使用 `docker compose logs --tail 100 web` 診斷。
- Docker 與通行碼減少風險，不能證明主機絕對安全；獨立入口限流與驗證留待下一階段。

設定依據：[Docker Compose 服務規格](https://docs.docker.com/reference/compose-file/services/)、
[uv 的 Docker 指南](https://docs.astral.sh/uv/guides/integration/docker/)。
