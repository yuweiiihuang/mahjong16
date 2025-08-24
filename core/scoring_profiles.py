# file: core/scoring_profiles.py
from __future__ import annotations
from typing import Dict

# 內建計分表（可由外部 JSON 覆蓋）
# 說明：
# - key 為台型代號；value 為該台型的「每次加台數」
# - 互斥/條件邏輯由 judge.py 控制（如：門清自摸=3 不再與門清/自摸重複）
PY_SCORING_TABLE: Dict[str, Dict[str, int]] = {
    "gametower_star31": {
        "dealer": 1,
        "menqing": 1,
        "zimo": 1,
        "menqing_zimo": 3,           # 門清自摸互斥於 menqing / zimo
        "flower": 1,                 # 見花見台（一張 1）
        "feng_pung": 1,              # 任意風刻 +1（見花見字）
        "dragon_pung": 1,            # 中/發/白刻 +1
        "kong_any": 1,               # 明槓/加槓 +1
        "kong_concealed": 2,         # 暗槓 +2
        "no_honor_no_flower": 2,     # 無字無花 +2（需門清，無花，整副無字）
        "hai_di": 1,                 # 海底撈月 +1（最後一張自摸）
        "qiang_gang": 1,             # 搶槓胡 +1（目前未在 judge 中使用旗標）
        # 常見型態/大牌（若之後實作可直接取用）
        "hun_yi_se": 4,
        "qing_yi_se": 8,
        "peng_peng_hu": 4,
        "ping_hu": 2,
        "xiao_san_yuan": 4,
        "da_san_yuan": 8,
        "xiao_si_xi": 8,
        "da_si_xi": 16,
        "di_hu": 16,
        "tian_hu": 24
    },
    "mj888": {
        "dealer": 1,
        "menqing": 1,
        "zimo": 1,
        "menqing_zimo": 3,
        "flower": 1,                 # 正花 +1（此內建未細分對位）
        "feng_pung": 1,              # 簡化後仍作 +1；如需圈風/門風拆解，外部 JSON 可自訂
        "dragon_pung": 1,
        "kong_concealed": 2,         # 暗槓 +2
        "gang_shang": 2,             # 槓上自摸 +2（含自摸）
        "hai_di": 1,
        "qiang_gang": 1,
        "hun_yi_se": 4,
        "qing_yi_se": 8,
        "peng_peng_hu": 4,
        "ping_hu": 2
        # MJ888 未定義：no_honor_no_flower
    }
}