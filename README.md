
# mahjong16 — 台灣 16 張麻將（可訓練 AI 專案骨架）

此版本已加入 **`drawn`（本巡摸到的一張，臨時第 17 張）** 的正確流程：

- 起手每家 16 張，**莊家多摸一張至 `drawn`**（開門 17 張）。
- 每巡開始先摸到 `drawn`（遇花自動補），然後從 `drawn` 或 `hand` 丟回 1 張。

目前提供：

- `core/`：環境與規則介面（已含 `drawn`、補花、丟牌；吃/碰/槓/胡與結算留 TODO）。
- `bots/`：隨機與啟發式範例。
- `rl/`：自我對弈與網路骨架（訓練需自行安裝 PyTorch）。
- `tests/`：基礎測試（含莊家 17 張與回合輪轉檢查）。

## 快速開始

```bash
pip install -r requirements.txt
python main.py
pytest -q
```

## 設計重點

- 狀態欄位：`hand`（16 張）、`drawn`（本巡摸到的一張或 `None`）、`flowers`、`melds`、`rivers`。
- API：`reset()` / `step(action)` / `legal_actions()`。
- 動作：目前僅 `DISCARD`（`from: "drawn"|"hand"`）與保留用的 `PASS`（在簡化版中不可於自己回合使用）。

## 專案目錄架構

```text
mahjong16/
├─ core/                  # 純規則與模擬（與 ML 解耦）
│  ├─ tiles.py            # 牌編碼／花處理／洗牌
│  ├─ ruleset.py          # 台麻 16 規則設定（是否含花、張數等）
│  ├─ env.py              # 單桌環境：reset/step/observation/legal_actions（含 drawn 流程）
│  └─ judge.py            # 合法性檢查、胡牌（五面子或刻子 + 眼睛）、結算（TODO）
├─ bots/
│  ├─ random_bot.py       # 隨機（測試用）
│  ├─ rulebot.py          # 規則／啟發式 Bot（baseline）
│  └─ mcts_bot.py         # IS-MCTS（預留；未來擴充）
├─ rl/
│  ├─ net.py              # Policy-Value Network（PyTorch，可選）
│  ├─ selfplay.py         # 產生自我對弈資料（可多進程）
│  ├─ buffer.py           # 重播佇列（Replay Buffer）
│  └─ train.py            # AlphaZero 式訓練循環（樣板）
├─ service/               # （可選）部署推論與模型匯出
│  ├─ infer_server.py     # gRPC／WebSocket 推論服務（預留）
│  └─ exporter.py         # 匯出 ONNX／TensorRT（預留）
├─ scripts/
│  ├─ eval_league.py      # 天梯／TrueSkill 評估（樣板）
│  └─ bench_sim.py        # 模擬吞吐量壓測
├─ tests/
│  └─ test_env_basic.py   # 基本不變式測試（含莊家 17 張與 drawn 輪轉）
├─ main.py                # CLI Demo：印出手牌與 drawn
├─ README.md
└─ requirements.txt
```
