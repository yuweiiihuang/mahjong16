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
