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
        "ting": 1,                    # 宣告聽牌 +1

        # 下列鍵值雖保留，但目前 judge.py 不採見花見字與風刻加台
        "flower": 1,                 # 見花見台（一張 1）【目前不使用】
        "feng_pung": 1,              # 任意風刻 +1（見花見字）【目前不使用】

        "dragon_pung": 1,            # 中/發/白「副露」刻 +1（尺寸大牌另算）
        "kong_any": 1,               # 明槓/加槓 +1（目前不使用）
        "kong_concealed": 2,         # 暗槓 +2（目前不使用）
        "no_honor_no_flower": 2,     # 無字無花 +2（目前不使用）
        "hai_di": 1,                 # 海底撈月 +1
        "qiang_gang": 1,             # 搶槓胡 +1（目前未在 judge 中使用旗標）

        # 常見型態/大牌
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
        "ting": 1,
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

# 顯示用標籤（score_with_breakdown 會使用）
SCORING_LABELS: Dict[str, str] = {
    "dealer": "莊家",
    "menqing": "門清",
    "zimo": "自摸",
    "menqing_zimo": "門清自摸",
    "ting": "聽牌",
    "flower": "見花見台",
    "feng_pung": "風刻",
    "dragon_pung": "三元牌",
    "kong_any": "槓牌",
    "kong_concealed": "暗槓",
    "no_honor_no_flower": "無字無花",
    "hai_di": "海底撈月",
    "qiang_gang": "搶槓胡",
    "gang_shang": "槓上開花",
    "hun_yi_se": "混一色",
    "qing_yi_se": "清一色",
    "peng_peng_hu": "碰碰胡",
    "ping_hu": "平胡",
    "xiao_san_yuan": "小三元",
    "da_san_yuan": "大三元",
    "xiao_si_xi": "小四喜",
    "da_si_xi": "大四喜",
    "di_hu": "地胡",
    "tian_hu": "天胡",
}
