
"""
判定/計分集中區：

- is_ready / shanten：計算向聽數（支援16張）
- can_chi / can_pon / can_kan / can_ron：吃碰槓胡合法性與優先權
- is_win_16: 胡牌判定（五刻子/順子 + 一組眼睛（將牌））
- settle_scores_stub: 結算（自摸/放槍、台數→點數）

目前為樣板與 TODO。
"""
from __future__ import annotations
from typing import List, Any

def is_win_16(hand: List[int], melds: List[Any], rules) -> bool:
    # TODO：實作五刻子/順子及一將判定；暫時返回 False（未胡）
    return False

def settle_scores_stub(state) -> List[int]:
    # TODO：依家規實作結算；暫以全零回傳
    return [0,0,0,0]
