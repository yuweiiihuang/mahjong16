# 離線牌譜紀錄與驗證

目前是第一階段：可選的引擎紀錄、版本化 JSON 格式及離線重播。
尚未啟用網頁自動存檔、SQLite、玩家戰績或重啟續局。

## 本機使用

使用專案虛擬環境，或將以下 `.venv/bin/python` 換成 `uv run --locked python`。

```bash
.venv/bin/python -m app.replay record /tmp/mahjong-hand.json --seed 7
.venv/bin/python -m app.replay verify /tmp/mahjong-hand.json
```

record 錄製並驗證一局 GreedyBot 對局，拒絕覆寫已有檔案。
verify 重新發牌、依序執行動作，檢查每一步狀態及完成局的計分明細/收付分。
這是引擎驗證，不是網頁重播播放器。

## 接入引擎

```python
import json
from pathlib import Path
from domain.gameplay.game_env import Mahjong16Env
from domain.gameplay.recording import HandRecorder, replay_hand
from domain.rules.ruleset import Ruleset

recorder = HandRecorder()
env = Mahjong16Env(Ruleset(), seed=7, recorder=recorder)
env.reset()
# 依正常路徑呼叫 env.step(action, pid=pid)，不直接修改 env 的牌局狀態。
document = recorder.document()
with Path('/tmp/hand-prefix.json').open('x', encoding='utf-8') as handle:
    json.dump(document, handle, ensure_ascii=False)
replayed = replay_hand(document)
```

每次 reset 新增一份紀錄，`document()` 回傳最新局的獨立 JSON 副本。
`records` 保留本次 recorder 的所有局；目前在記憶體中，不具備當機後保存能力。
未提供 recorder 的既有呼叫不增加紀錄或計分工作。

## 格式與界線

- 記錄格式版本、實際 domain 原始碼 SHA-256、解析後規則、實際計分表、局 ID。
- 保存完整初始牌牆與風位/莊家設定，不依賴 seed 還原連續牌局的亂數進度。
- 初始狀態含發牌/補花結果；每一步記 actor、action、反應窗口、前後狀態校驗值、
  引擎 reward、裁決結果及窗口提前結束時未回覆的座位。
- 完成局保存原有計分引擎算出的台數、明細和收付分。
  `rewards` 是 env.step 的原始回傳，並不等於最終收付分或已定義的 RL reward。
- 輸出是私有完整牌譜，含暗牌及牌牆，不能放在 ui/web 或送進玩家 snapshot。
- 不含玩家身份、控制來源、時間、玩家可見觀察或 RL next_obs；第二階段再接應用層資訊。
- `incomplete` 只代表已錄下的步驟前綴，不能算成流局、輸局或可恢復房間。
- 重播只接受相同格式與 domain 原始碼版本；SHA-256 用來識別版本與偵測不一致，
  不是簽章，也不是防止惡意偽造牌譜的認證機制。
- 啟用紀錄時，只接受合法操作；偵測到直接修改引擎狀態則拒絕繼續記錄。
  自訂程式需要在 reset 的正常發牌流程安排局面，不應錄製途中偷偷改牌。

詳見 [後續規劃](architecture/game-recording-plan.md)。
