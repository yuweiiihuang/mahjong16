# Web UI 回歸

在專案根目錄啟用 `.venv`，執行完整 Python 與 Node 回歸：

```bash
pytest -q
node --test tests/web/*.mjs
```

Node 集合涵蓋排序、按鈕、設定、結算、牌面與幾何等案例。
它會載入 `sort_drag.browser.mjs`，但不會呼叫其中的 `checkSortDrag`；
實際拖拉、WebGL 呈現及觸控須另做以下瀏覽器驗收。

多人房間、手牌隔離、重送／過期操作與重連：

```bash
pytest -q tests/web/test_multiplayer.py
```

包含真實本機 HTTP 測試，需要允許程式監聽本機連接埠。
加入、重新整理與兩位真人輪流出牌仍需瀏覽器驗收；部署與限制見
`docs/multiplayer.md`。

排序邏輯：

```bash
node --test tests/web/test_hand_sort.mjs
```

3D 檢查：花牌／副露碰撞、四家完整三排牌河與手牌／副露／花牌的碰撞、槓牌 3+1 疊放與翻面、中央五區塊指示器及換座後的操作方位高亮：

```bash
node --test tests/web/test_table_layout.mjs
```

使用實際牌體建立與座位旋轉邏輯檢查包圍盒，不需要 WebGL；視覺排版仍需瀏覽器驗收。

真實拖拉（Codex CUA REPL；先啟動 `python -m app.web --port 8000`）。
已有使用中的牌桌時，另選測試埠與獨立 `--record-db`，並替換下列 URL。

```javascript
let testTab = await cua.createBrowserTab('iab', 'http://localhost:8000/', {visible: false});
```

取得分頁後，在下一次 REPL 呼叫執行；將 `/absolute/path/to/mahjong16`
替換為本次 checkout 的絕對路徑：

```javascript
let regression = await import('/absolute/path/to/mahjong16/tests/web/sort_drag.browser.mjs');
nodeRepl.write(await regression.checkSortDrag(testTab, 24));
await testTab.close();
```

測試使用實際指標輸入，檢查往返拖拉會換位、放開後不鎖住下一次操作、
沒有殘留的 translate 位移、ARIA 順序正確、四張牌不遺失或重複、
未儲存時背景手牌不變，以及關閉設定後捨棄草稿。
不按「儲存」，不改動使用者的偏好，也不出牌。

採用 SortableJS 1.15.7 core（MIT），官方來源：
https://github.com/SortableJS/Sortable/tree/1.15.7
本地模組與授權放在 `ui/web/vendor/`。
四張牌不使用換位動畫，讓下一次抓牌的槽位保持固定。

這項回歸不取代人工手感驗收，也未涵蓋實機觸控。
UI 變更必須等使用者測試確認後才能推送。

續局與紀錄 API：

```bash
pytest -q tests/web/test_table_recovery.py tests/web/test_record_api.py
pytest -q tests/web/test_practice_sessions.py
node --test tests/web/test_session_chart.mjs
```

瀏覽器驗收須使用隔離資料庫：完成一局並進入下一局，從房間資訊開啟
「牌局紀錄／續局」，確認胡牌摘要及原牌桌重播上／下一步、進度拉桿與四家視角。
單排播放器檢查：播放／暫停切換、1×沿用牌桌節奏、倍速切換不產生重複計時器、
到終局自動停止、手動跳轉暫停；桌面與窄版手機橫向均不換行或橫向溢出。
東南西北視角按鈕反白標示目前風位；切換後停在相同步數，吃碰提示及出牌標記跟著座位轉換。
重播中用滑鼠／鍵盤／觸控均不能出牌、改名或開新局；退出才恢復目前牌桌。
多人房間在重播期間仍繼續，退出需取得最新版本；斷線時保留重試出口。
重播期間目前牌桌的手牌與分數不應改變；未完成局不能重播。
停止並以相同埠／資料庫重新啟動測試服務，用原瀏覽器從紀錄恢復未完成局，
確認局次、手牌、副露、分數與反應選擇保留。多人桌由原玩家分別恢復，
驗證同一房號共用一桌及原座位，不讓陌生玩家讀取紀錄。
另檢查桌面與手機橫向、切回背景分頁、GPU context 恢復及手機長按；
Node 的 refresh/context-menu 回歸不代表實機 WebGL／iOS 行為已驗證。

單人 Session 驗收：首局未完時重開按鈕反灰，重新整理或重啟仍是同一副牌；
完成一局後建立新 Session，從卡片切回舊桌仍保留分數，未完新桌會阻止再次開桌。
展開卡片檢查四家走勢、統計、逐局結算與重播；百局以上的統計不能被近期100局截斷。
手機橫向檢查卡片捲動、統計表橫向捲動及續局按鈕可操作。

吃碰槓提示：確認單人及多人只有其他三家已裁決的動作會顯示在玩家卡片朝桌內的一側，
自己操作不提示。吃／碰／槓沿用操作色票，實色底75%不透明、白字保持完全不透明，
對家提示放在名牌右側；左家在右側、右家在左側。
沒有陰影、不攔截手牌點擊，約1.8秒後消失。
他家胡牌／自摸使用紅色提示並顯示「胡」或「自摸」，先顯示完整1.8秒再開結算；
自己的胡牌／自摸不提示，已結束的重複輪詢不再播報。
檢查手機橫向、四家位置、換座及調整視窗後仍在安全區；未決吃碰與重複輪詢不重播。
