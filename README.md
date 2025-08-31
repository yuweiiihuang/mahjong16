# mahjong16 — 台灣 16 張麻將環境骨架

`mahjong16` 提供可擴充的台灣 16 張麻將模擬環境，適合作為 AI 對局與強化學習的基礎。

## 功能特色

- **drawn 模式**：每位玩家固定 16 張手牌，輪到自己時先摸成 `drawn` 再決定棄牌，莊家開局即持有 `drawn`。
- **反應視窗與優先權**：棄牌後依距離與「胡>槓>碰>吃」排序，允許其他玩家插入行動。
- **尾牌留置**：支援固定留牌或「一槓一」模式，若牆剩餘牌不足則流局。
- **胡牌判定（純函式）**：`core.hand.is_win_16` 實作「五面子一眼」判定；另提供 `waits_*` 計算聽牌等待。
- **計分引擎（可換表）**：`core/scoring/engine.py` 依 `taiwanese_mahjong_scoring.json` profiles 計分；以 `ScoringContext` 注入環境快照與計分表。
- **範例對局 bot**：提供隨機策略與簡單啟發式兩種 bot 供測試或自我對弈。
- **強化學習骨架**：包含 policy‑value 網路、Replay Buffer 與自我對弈資料產生（需自行安裝 PyTorch）。

## 快速開始

```bash
pip install -r requirements.txt
python main.py      # CLI 範例
pytest -q           # 執行測試
```

## 設計重點

- 核心規則與模擬位於 `core/`，與 bots、RL 模組解耦。
- 環境 API：`reset()` 初始化；`legal_actions()` 產生合法動作；`step(action)` 進行棄牌或反應並回傳新狀態。
- 手牌判定與計分解耦：`core/hand` 僅提供純計算；計分 IO 僅在 `core/scoring/tables`，計分邏輯在 `core/scoring/engine`。
- 以 `ScoringContext` 封裝環境必要快照（玩家手牌/副露/來源等），利於注入與單元測試。
- 狀態欄位包含 `hand`、`drawn`、`flowers`、`melds`、`river` 等，方便後續擴充計算。

## 專案架構

```text
mahjong16/
├─ core/                          # 規則、模擬與計分核心
│  ├─ tiles.py                    # 牌編碼、洗牌、轉字串
│  ├─ ruleset.py                  # 場規設定（含尾牌留置、計分 profile 名稱）
│  ├─ env.py                      # 單桌環境：reset/step/legal_actions
│  ├─ hand.py                     # 純手牌判定：is_win_16 / waits_*
│  └─ scoring/
│     ├─ engine.py                # 計分引擎（score_with_breakdown）
│     ├─ tables.py                # 計分表載入（JSON profiles + labels）
│     └─ types.py                 # ScoringTable / ScoringContext 型別
├─ app/                           # Demo 執行與互動策略
│  ├─ runtime.py                  # Demo 執行流程（預載計分表、顯示結果）
│  ├─ strategies.py               # Auto/Human 策略（使用 hand.waits_*）
│  └─ formatting.py               # CLI 顯示用格式化工具
├─ ui/                            # Rich 終端 UI
│  └─ console.py                  # 公開資訊與攤牌畫面渲染
├─ bots/                          # 範例對局 bot
│  ├─ random_bot.py               # 隨機策略
│  ├─ rulebot.py                  # 極簡啟發式
│  └─ greedy.py                   # 貪婪啟發式策略
├─ rl/                            # 自我對弈與訓練骨架
│  ├─ net.py
│  ├─ selfplay.py
│  ├─ buffer.py
│  └─ train.py
├─ scripts/                       # 評估與壓測（樣板）
│  ├─ eval_league.py
│  └─ bench_sim.py
├─ tests/                         # 單元測試
│  ├─ test_env_basic.py
│  ├─ test_reaction_basic.py
│  ├─ test_deadwall.py
│  ├─ test_tsumo.py
│  ├─ test_win_basic.py
│  └─ test_scoring.py
├─ taiwanese_mahjong_scoring.json # 計分 profiles 與標籤
├─ main.py                        # CLI Demo 入口
└─ requirements.txt
```

## 待辦事項

- 加槓 / 暗槓、計分與結算、服務部署與模型匯出。
- 擴充 bot 與搜尋／策略演算法。
- 完成 `train.py` 強化學習流程。
