# 舊 Web UI 移除紀錄

自 2026-10-01 起，主要 Web UI 採用 `daece1f` 的青禾桌面。
後續修改以 `ui/web/`、`app/web.py` 與 `tests/web/` 為準，主專案只保留此版本。

## Git 歷史備份

舊版 `gui`、`ui-20260615`、本地 `webui` 與原遠端 `webui` 的歷史
保留於本地 `.archive/legacy-webui-history-20261001.bundle`。
本地與遠端舊 UI 分支已移除；備份不推送，不作為開發基線。
可使用 `git bundle list-heads` 查閱備份，或從 bundle fetch 指定分支以復原。

## 尚未提交的檔案

React/Vite baseline、session API、測試、原型、設計草稿與 README 的唯一副本
保留在本地 `.archive/legacy-webui-20261001/`，不納入 Git、不推送。
主專案已移除 `app/web/`、`web/`、`prototypes/`、`tests/app/web/`
與 `scripts/run_web_api.py` 等舊版入口。
