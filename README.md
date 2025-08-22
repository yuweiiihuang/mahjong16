
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

## 授權

MIT License
