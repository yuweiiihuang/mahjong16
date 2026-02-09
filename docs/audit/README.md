# 規則完整性盤點流程

## 目的
以 `taiwan_base` 為主基準，盤點台灣十六張規則在「文件、設定、引擎、測試」四層的覆蓋情況。

## 輸入
- 規格表：`docs/audit/rule_catalog.csv`
- 計分設定：`configs/scoring/profiles/*.json`
- 引擎程式：`domain/scoring/rules/*.py` 與 `domain/gameplay/*.py`
- 測試：`tests/**/test_*.py`

## 執行
```bash
python scripts/audit_rule_coverage.py
```

## 輸出
- `reports/rule_coverage.json`
- `reports/rule_coverage.md`

## 缺漏分級
- `P0`：必備規則缺漏（會造成核心結算錯誤）
- `P1`：必備規則有條件偏差（保留給後續擴充）
- `P2`：可選變體未實作
- `P3`：文件/註解/測試覆蓋不足

## 驗收門檻
改動規則後至少執行：
```bash
pytest -q
python scripts/audit_rule_coverage.py
```
