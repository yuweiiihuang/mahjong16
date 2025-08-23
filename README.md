# mahjong16 — 台灣 16 張麻將 AI 專案骨架

`mahjong16` 提供一個可用於訓練與測試 AI 的台灣 16 張麻將環境。本專案著重於 **drawn** 流程與回合輪轉，方便未來擴充吃、碰、槓與胡牌邏輯。

## 功能特色

- 起手每家 16 張，莊家額外摸一張成為 **`drawn`**。
- 每巡先摸至 `drawn`（自動補花），再從 `drawn` 或 `hand` 棄一張。
- 環境 API：`reset()` / `step(action)` / `legal_actions()`。
- 目前支援動作：`DISCARD` 與保留用 `PASS`（自己回合不可使用）。
- 提供隨機與規則 bot，以及 RL 訓練骨架。

## 快速開始

```bash
pip install -r requirements.txt
python main.py
pytest -q
```

## 設計重點

- 狀態欄位：`hand`（16 張）、`drawn`（本巡摸到的一張或 `None`）、`flowers`、`melds`、`rivers`。
- 將規則與 ML 解耦，核心環境位於 `core/`。
- `core/env.py` 實作 `drawn` 流程與回合輪轉；`judge.py` 預留胡牌與結算。

## 專案架構

```text
mahjong16/
├─ core/                  # 規則與模擬
│  ├─ tiles.py            # 牌編碼／花處理／洗牌
│  ├─ ruleset.py          # 台麻 16 規則設定（含花與張數）
│  ├─ env.py              # 單桌環境：reset/step/observation/legal_actions
│  └─ judge.py            # 合法性檢查、胡牌與結算（預留）
├─ bots/                  # 範例對局 bot
│  ├─ random_bot.py       # 隨機策略
│  ├─ rulebot.py          # 規則／啟發式基線
│  └─ mcts_bot.py         # IS-MCTS（預留）
├─ rl/                    # 自我對弈與訓練骨架（需自行安裝 PyTorch）
│  ├─ net.py              # Policy-Value Network
│  ├─ selfplay.py         # 產生自我對弈資料
│  ├─ buffer.py           # Replay Buffer
│  └─ train.py            # AlphaZero 式訓練流程
├─ scripts/               # 評估與測試腳本
│  ├─ eval_league.py      # TrueSkill 評估
│  └─ bench_sim.py        # 模擬吞吐量壓測
├─ tests/                 # 基礎單元測試
│  └─ test_env_basic.py   # 檢查莊家 17 張與 drawn 輪轉
├─ main.py                # CLI Demo
└─ requirements.txt
```

## 待辦事項

- 吃／碰／槓／胡牌判定與結算。
- 服務部署與模型匯出。
- 改進規則 bot 與搜尋演算法。

