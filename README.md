# mahjong16 — 台灣 16 張麻將

![雙紅紅中與 mahjong16 字標](docs/brand-lockup.svg)

mahjong16 是可以自己架設的台灣 16 張麻將網頁牌桌。單人練習時有三位電腦玩家陪打。
跟朋友玩就開房分享網址，每桌最多四位真人，空位由電腦補上。牌桌會保存對局，
下次可以回到瀏覽器繼續打，也能重播已完成的牌局。

- [快速開始](#快速開始)
- [自行部署](docs/docker.md)

## 快速開始

安裝 Python 3.13+ 和 `uv` 後，到專案根目錄執行下面兩行。

```bash
uv sync --locked
uv run --locked python -m app.web --port 8000
```

在這台電腦開啟 [http://127.0.0.1:8000](http://127.0.0.1:8000) 就能直接進桌。
這樣啟動的牌桌只接受本機連線。

## 自行部署

部署時先準備全站通行碼，把私有牌譜資料庫放在持久化資料卷。通行碼檔案放在專案與網頁目錄之外，
只讓服務帳號讀取。用 Compose 建置和啟動牌桌、更新或回復版本、備份和還原牌譜的步驟都在
[Docker 牌桌指南](docs/docker.md)。

分享牌桌給外部使用者時，請用 HTTPS 並啟用存取驗證。如果想讓朋友用各自的帳號登入，
可以設定可信閘道。步驟見 [Pocket ID／Passkey 部署指南](docs/pocket-id.md)。

伺服器預設把私有牌譜存到 `data/hands.sqlite3`，也可以用 `--record-db` 指定位置。
每個服務實例各用一份資料庫。伺服器重啟後，同一引擎版本的牌局可從網頁的牌局紀錄續局。
引擎換版後，舊牌譜可能無法續局。

完整牌譜有暗牌和牌牆，只供管理者離線存取。執行 `python -m app.replay --help` 可查看如何查詢、
備份、離線驗證和匯出。詳見 [牌譜保存、續局與重播](docs/hand-recording.md)。

## 玩法與場規

進桌後可選單人練習。要跟朋友玩，就從「朋友連線」開房，再把邀請網址傳給朋友。
選好手牌後按「出牌」或 Enter，也可以雙擊牌面。畫面會依牌局顯示可以選的吃、碰、槓、胡或過。

牌桌會自動補花，也會顯示聽牌提示、台數明細和四家點數結算。按「下一局」會沿用累計點數，
並依牌局進度更新莊家和圈風。電腦上可直接玩，手機請橫放。瀏覽器須支援 WebGL。
開房及連線方式見 [朋友連線](docs/multiplayer.md)。

共用引擎負責規則、反應判定和計分。花牌、尾牌留置（固定或一槓一）、座次和計分都可透過場規設定。
結算以引擎和現行設定檔為準。台數說明見 [台灣麻將台數參考](docs/台灣麻將台數計算表.md)。

## 開發與無介面引擎

本專案持續維護以下兩個無介面入口。在原始碼目錄執行 `uv sync --locked` 後，
就能直接從 Python 跑牌局，無需啟動網頁服務或等待真人輸入。

- 跑單局用 `app.episode.HandEpisode`。用 `current()` 取得目前行動座位看得到的資訊和合法動作，
  再用 `act()` 驗證並執行動作。打完後用 `payments()` 取得四席收付。
- 跑多局或整將用 `app.session.SessionService`。傳入引擎、桌次管理、各座位策略和計分設定後，
  `run()` 會跑完對局並回傳逐局摘要。無介面呼叫可省略桌面、摘要和進度 adapter。

用相同的 seed 和場規可以重現同一個開局。

```python
from app.episode import HandEpisode
from domain import Ruleset

episode = HandEpisode(seed=1234, rules=Ruleset(rule_profile="common"))
observation = episode.current()
```

用 `Ruleset.rule_profile` 選擇 `configs/rules/profiles/` 裡的場規，預設是 `common`。
計分表在 `configs/scoring/profiles/`。要用自己的表，可用 `Ruleset.scoring_overrides_path` 指定。
修改計分時請補上對應的回歸測試。

```bash
uv run --locked pytest -q
node --test tests/web/*.mjs
```

實際拖拉、WebGL 與手機觸控驗收見 [Web 測試指南](tests/web/README.md)。
模組分工見 [架構圖](docs/architecture/diagram.png)（[Graphviz 來源](docs/architecture/diagram.gv)）。
模擬、效能及對局分析工具見 [scripts 指南](scripts/README.md)。

## 授權與問題回報

專案目前尚未宣告原始碼授權。再散布或其他需要授權的用途，請先向維護者確認。
第三方素材各有自己的授權。Three.js 和 SortableJS 的授權在 `ui/web/vendor/`。
牌面從哪裡來、改過哪些地方，見 [SVG 來源](ui/web/assets/tiles/fonts/README.md)。
維基轉載素材依檔案上的 CC BY-SA 標示使用。

請透過既有協作管道回報問題，附上程式版本、重現命令或步驟，以及預期和實際的結果。
如果是瀏覽器問題，也請附上裝置和版本。送出前請移除通行碼、Cookie 和私有牌譜。
