# 青禾麻將

青禾麻將是一套可自行部署的台灣 16 張麻將網頁牌桌。你可以和三位電腦玩家單人練習，
也可以開房邀請朋友連線。每桌最多四位真人，空位由電腦補上。牌桌會保存對局，
可從瀏覽器續局或重播已完成的牌局。

- [本機試玩](#本機試玩)
- [自行部署](docs/docker.md)

## 本機試玩

準備 Python 3.13+ 和 `uv`，從專案根目錄啟動牌桌。

```bash
uv sync --locked
uv run --locked python -m app.web --port 8000
```

開啟 [http://127.0.0.1:8000](http://127.0.0.1:8000)。這個指令只在本機開放牌桌，
試玩時可直接進桌。

## 自行部署

從 [Docker 牌桌指南](docs/docker.md) 開始。指南說明如何用 Compose 建置與啟動牌桌、
備份與還原牌譜，以及更新與回復版本。部署時設定全站通行碼，並將私有牌譜資料庫存放在
持久化資料卷。通行碼檔案放在專案與網頁目錄之外，只授權服務帳號讀取。

對外分享請使用 HTTPS 並啟用存取驗證。需要讓朋友以各自的帳號登入時，
可依 [Pocket ID／Passkey 部署指南](docs/pocket-id.md) 設定可信閘道。

伺服器預設將私有牌譜保存至 `data/hands.sqlite3`，可用 `--record-db` 指定位置。
重啟後可從網頁的牌局紀錄繼續相同引擎版本的牌局。引擎換版可能影響既有牌譜的續局相容性。
完整牌譜含暗牌與牌牆，由管理者離線存取。使用 `python -m app.replay --help` 查看查詢、
備份、離線驗證與匯出命令。各服務實例使用獨立的資料庫。
詳見 [牌譜保存、續局與重播](docs/hand-recording.md)。

## 玩法與場規

在牌桌選擇單人練習，或開啟「朋友連線」建立房間並分享邀請網址。
點選手牌後按「出牌」，也可雙擊牌面或按 Enter 出牌。吃、碰、槓、胡、過依合法動作顯示。
牌桌支援自動補花、聽牌提示、台數明細和四家點數結算。「下一局」保留累計點數並推進莊家與圈風。
瀏覽器需支援 WebGL。桌面可直接遊玩，手機請橫向使用。詳見 [朋友連線](docs/multiplayer.md)。

規則、反應判定與計分由共用引擎處理。場規可設定花牌、尾牌留置模式（固定或一槓一）、
座次與計分設定。查看 [台灣麻將台數參考](docs/台灣麻將台數計算表.md)；
實際結算以引擎與現行設定檔為準。

## 開發與無介面引擎

在原始碼 checkout 執行 `uv sync --locked` 後，即可從 Python 使用持續維護的無介面引擎。
兩個入口都可在程序內執行，無需啟動網頁服務或等待真人輸入。

- 單局使用 `app.episode.HandEpisode`。`current()` 取得當前座位可見的觀測與合法動作。
  `act()` 驗證並執行動作，終局以 `payments()` 取得四席收付。
- 多局或整將使用 `app.session.SessionService`。傳入引擎、桌次管理、各座位策略與計分設定，
  由 `run()` 推進對局並回傳逐局摘要。無介面呼叫可省略桌面、摘要與進度 adapter。

以下範例用固定 seed 和場規重現一局的開局。

```python
from app.episode import HandEpisode
from domain import Ruleset

episode = HandEpisode(seed=1234, rules=Ruleset(rule_profile="common"))
observation = episode.current()
```

以 `Ruleset.rule_profile` 選擇 `configs/rules/profiles/` 下的場規，預設為 `common`。
計分表位於 `configs/scoring/profiles/`，可透過 `Ruleset.scoring_overrides_path` 指定自訂表。
修改計分時請補上對應的回歸測試。

```bash
uv run --locked pytest -q
node --test tests/web/*.mjs
```

實際拖拉、WebGL 與手機觸控驗收見 [Web 測試指南](tests/web/README.md)。
模組分工見 [架構圖](docs/architecture/diagram.png)（[Graphviz 來源](docs/architecture/diagram.gv)）。
模擬、效能及對局分析工具見 [scripts 指南](scripts/README.md)。

## 授權與問題回報

目前 repository 尚未宣告專案原始碼授權。第三方素材依各自的授權條款提供。
Three.js、SortableJS 的授權位於 `ui/web/vendor/`。牌面來源與修改見
[SVG 來源](ui/web/assets/tiles/fonts/README.md)，維基轉載另依其檔案中的 CC BY-SA 標示。
需要再散布或其他使用授權時，請先向維護者確認。

回報問題時請附程式版本、重現命令或操作、預期與實際結果。瀏覽器問題另附裝置與版本。
請透過既有協作管道回報，並移除通行碼、Cookie 與私有牌譜。
