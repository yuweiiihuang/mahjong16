# Mahjong16 SDK 升級指引

此版本將外部擴充功能的主要進入點集中到全新的 `sdk` 封裝。以下列出
從舊版升級所需的調整與常見注意事項。

## 核心變更

* 新增 `sdk/__init__.py` 作為**唯一支援的公開 API** 入口，整合環境、
  規則、計分、Session 服務與策略工廠等原散落於 `domain/`、`app/` 的
  類別與函式。
* `mahjong16/interfaces/cli/entrypoint.py` 移植原 `main.py` 解析參數與
  執行流程；`main.py` 僅保留薄層轉呼叫，方便其他程式以模組方式載入。
* `bots/`、`ui/`、`rl/` 以及提供給玩家或自動化使用的 scripts/tests 皆改
  由 `sdk` 取得所需功能，避免直接耦合內部實作。
* 舊的 `core` re-export 仍存在，但現在會顯示警示訊息並轉向 `sdk`。

## 升級範例

舊版：

```python
from domain import Mahjong16Env, Ruleset
from domain.scoring.tables import load_scoring_assets
```

新版：

```python
from sdk import Mahjong16Env, Ruleset, load_scoring_assets
```

CLI 使用者亦可直接呼叫：

```bash
python -m mahjong16.interfaces.cli --bot greedy --hands 4
```

若仍透過 `python main.py` 啟動，行為與舊版相同。

## 介面分層與 Port

* `sdk` 只轉出穩定介面，內部邏輯仍置於 `app/`（Application 層）與
  `domain/`（Domain 層）。
* Session 相關的 `TableViewPort`、`HandSummaryPort`、`ProgressPort` 等
  Protocol 由 SDK 提供，可供 UI/bot/CLI 等外部介面實作。
* Bot 與 UI 如需判斷聽牌或計算剩餘張數，請改用
  `sdk.waits_after_discard_17`、`sdk.visible_count_global` 等 helper。

## 相容性與型別檢查

* 測試已更新為改用 `sdk` 匯入主要類別，確保公開 API 可滿足使用需求。
* mypy/pyright 等型別檢查若引用舊的 `domain.*`、`app.*`，請逐一改為
  `sdk.*`；僅限開發核心模組時才應直接依賴內部層級。

如需了解新的依賴方向，可參考 `docs/architecture/diagram.gv` 的更新圖示。
