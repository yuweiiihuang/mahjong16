import pytest

from core import Mahjong16Env, Ruleset
from core.judge import settle_scores_stub
from core.tiles import tile_to_str


def _tid(label: str) -> int:
    """以 tile_to_str 反查牌面字串的 tile id。"""
    for i in range(128):
        if tile_to_str(i) == label:
            return i
    raise AssertionError(f"Unknown tile label: {label}")


def _fresh_env(include_flowers=True):
    rules = Ruleset(include_flowers=include_flowers, dead_wall_mode="fixed", dead_wall_base=16)
    env = Mahjong16Env(rules, seed=0)
    env.reset()
    return env


def _set_winner_basic(env, pid=0, win_source="RON"):
    env.winner = pid
    env.win_source = win_source
    env.turn = pid
    env.phase = "DONE"
    # 重設必要欄位（不要用 setdefault，避免殘留 reset 時的 drawn）
    p = env.players[pid]
    p["hand"] = p.get("hand", [])
    p["drawn"] = None
    p["melds"] = p.get("melds", [])
    p["flowers"] = p.get("flowers", [])
    p["river"] = p.get("river", [])


def test_menqing_tsumo_is_3_only():
    """門清自摸 → 3 台（不與門清/自摸重複）；避免無字無花+2 介入，手牌放一張風牌。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="TSUMO")
    p = env.players[0]
    p["melds"] = []  # 門清
    p["flowers"] = []               
    p["hand"] = (
        [_tid("1W")]*4 + [_tid("2W")]*4 + [_tid("3W")]*4 + [_tid("4D")]*3 + [_tid("E")]
    )
    p["drawn"] = _tid("E")
    # 非海底
    env.wall = [0] * (env.rules.dead_wall_base + 1)
    rewards = settle_scores_stub(env)
    assert rewards[0] == 3 and sum(rewards) == 3


def test_tsumo_non_closed_is_1():
    """自摸但非門清（有碰/槓）→ +1。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="TSUMO")
    p = env.players[0]
    # 有一組碰（數牌），非門清；用 1W 碰，露出 3 張 1W
    p["melds"] = [{"type": "PONG", "tiles": [_tid("1W")] * 3}]
    p["flowers"] = []
    p["hand"] = [
        _tid("1W"), _tid("2W"),
        _tid("4W"), _tid("5W"), _tid("6W"),
        _tid("2D"), _tid("3D"), _tid("4D"),
        _tid("5D"), _tid("6D"), _tid("7D"),
        _tid("9B"), _tid("9B"),
    ]
    p["drawn"] = _tid("3W")                 
    env.wall = [0] * (env.rules.dead_wall_base + 10)  # 不是海底
    rewards = settle_scores_stub(env)
    assert rewards[0] == 1


def test_menqing_ron_is_1():
    """門清 → +1。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = []     # 門清
    p["flowers"] = []
    p["hand"] = [
        _tid("9W"),
        _tid("1W"), _tid("2W"), _tid("3W"),
        _tid("4W"), _tid("5W"), _tid("6W"),
        _tid("2D"), _tid("3D"), _tid("4D"),
        _tid("5D"), _tid("6D"), _tid("7D"),
        _tid("2B"), _tid("3B"), _tid("4B"),
    ]
    p["drawn"] = None   # 放槍胡：贏家自己沒有 drawn
    rewards = settle_scores_stub(env)
    assert rewards[0] == 1


def test_dragon_pung():
    """三元牌 +1"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = [
        {"type": "PONG", "tiles": [_tid("E")] * 3},  # 風刻
        {"type": "PONG", "tiles": [_tid("C")] * 3},  # 三元刻（中）
    ]
    p["flowers"] = []
    p["hand"] = [
        _tid("4D"), _tid("5D"), _tid("6D"),
        _tid("7B"), _tid("8B"), _tid("9B"),
        _tid("1D"), _tid("1D"), _tid("1D"), _tid("2W")
    ]
    rewards = settle_scores_stub(env)
    assert rewards[0] == 1


def test_haitei_tsumo_plus_one():
    """海底撈月 +1（最後一張牌自摸）。此例同時應有『自摸 +1』，總計 2。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="TSUMO")
    p = env.players[0]
    p["melds"] = [{"type": "PONG", "tiles": [_tid("1W")] * 3}]  # 打破門清 → 只計自摸1 + 海底1
    p["flowers"] = []
    p["hand"] = [_tid("1W")]*2 + [_tid("2W")]*2 + [_tid("3W")]*2 + [_tid("3B")]*3 + [_tid("4B")]*3 + [_tid("E")]
    p["drawn"] = _tid("E")
    # 牆牌數量 = 尾牌留置 → 海底
    reserved = env.rules.dead_wall_base
    env.wall = [0] * reserved
    rewards = settle_scores_stub(env)
    assert rewards[0] == 2


def test_peng_peng_hu_ron_from_discard():
    """碰碰胡（榮和補牌）：手牌少一張，靠別家丟的最後一張補成全刻 + 將 → +4。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]

    # 有一組數牌 PONG 打破門清（且非字牌，避免疊其他台）
    p["melds"] = [{"type": "PONG", "tiles": [_tid("1W")] * 3},
                  {"type": "PONG", "tiles": [_tid("2W")] * 3},]
    p["flowers"] = []

    # 手牌先放 3 組刻 + 1 組「差一張就成刻」 + 1 對（總共 13 張）
    # 這裡差的那張，等會用 last_discard 來補。
    p["hand"] = (
        [_tid("3W")] * 3 +   # 刻
        [_tid("2D")] * 3 +   # 刻
        [_tid("3D")] * 2 +   # 差一張 → 等會用 RON 補成刻
        [_tid("5W")] * 2     # 對子
    )
    # 指定別家剛丟出來、被我們榮的那張（補上面少的 3D）
    env.last_discard = {"player": 1, "tile": _tid("3D")}

    rewards = settle_scores_stub(env)
    assert rewards[0] == 4


def test_ping_hu_is_2():
    """平胡（全順子 + 一對，副露不可含 PONG/GANG，可含 CHI）→ +2。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    # 兩組 CHI 打破門清（允許 CHI）
    p["melds"] = [
        {"type": "CHI", "tiles": [_tid("1W"), _tid("2W"), _tid("3W")]},
        {"type": "CHI", "tiles": [_tid("4W"), _tid("5W"), _tid("6W")]},
    ]
    p["flowers"] = []
    # 手牌能拆成 3 組順 + 1 對（11 張）
    p["hand"] = [
        _tid("2D"), _tid("3D"), _tid("4D"),
        _tid("5D"), _tid("6D"), _tid("7D"),
        _tid("2B"), _tid("3B"), _tid("4B"),
        _tid("9W"), _tid("9W"),
    ]
    rewards = settle_scores_stub(env)
    assert rewards[0] == 2


def test_qing_yi_se_only_8():
    """清一色 → +8；加入一組 CHI 與一組數牌 PONG 打破平胡/門清，避免疊其他台。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    # 同一花色之 CHI + PONG，避免平胡
    p["melds"] = [
        {"type": "CHI", "tiles": [_tid("3W"), _tid("4W"), _tid("5W")]},
        {"type": "PONG", "tiles": [_tid("2W")] * 3},
    ]
    p["flowers"] = []
    # 手牌全部同一花色（萬），且不超過四張同牌（總手牌 11 張）
    p["hand"] = [_tid("1W")]*3 + [_tid("6W")]*3 + [_tid("7W")]*3 + [_tid("8W")]*2
    rewards = settle_scores_stub(env)
    assert rewards[0] == 8


def test_hun_yi_se_only_4():
    """混一色 → +4；同一花色 + 至少一組字牌（僅作將），避免風刻/三元刻與平胡。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = [
        {"type": "CHI", "tiles": [_tid("3W"), _tid("4W"), _tid("5W")]},
        {"type": "PONG", "tiles": [_tid("2W")] * 3},
    ]  # 打破平胡，也不門清
    p["flowers"] = []
    # 單一花色（萬） + 字牌作將（例如東東），總手牌 11 張
    p["hand"] = [_tid("1W")]*4 + [_tid("6W")]*3 + [_tid("7W")]*2 + [_tid("E")]*2
    rewards = settle_scores_stub(env)
    assert rewards[0] == 4


def test_xiao_san_yuan_only_4():
    """小三元 → +4；兩組三元刻 + 第三色作將；避免副露三元刻導致 +1 疊加。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    # 只放一組 CHI 打破門清，三元刻一律放在手牌
    p["melds"] = [{"type": "CHI", "tiles": [_tid("1W"), _tid("2W"), _tid("3W")]}]
    p["flowers"] = []
    p["hand"] = (
        [_tid("C")] * 3 +  # 中中中
        [_tid("F")] * 3 +  # 發發發
        [_tid("P")] * 2 +  # 白白（將）
        [_tid("4D")] * 3 + [_tid("5B")] * 3  # 其他墊牌，避免清/混一色
    )
    rewards = settle_scores_stub(env)
    assert rewards[0] == 4


def test_da_san_yuan_only_8():
    """大三元 → +8；三元皆刻（均放手牌）；避免副露三元刻的 +1 疊加。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = [{"type": "CHI", "tiles": [_tid("1W"), _tid("2W"), _tid("3W")]}]  # 打破門清
    p["flowers"] = []
    p["hand"] = (
        [_tid("C")] * 3 + [_tid("F")] * 3 + [_tid("P")] * 3 +
        [_tid("4D")] * 3 + [_tid("5B")] * 2
    )
    rewards = settle_scores_stub(env)
    assert rewards[0] == 8


def test_xiao_si_xi_only_8():
    """小四喜 → +8；三風刻 + 第四風作將（均放手牌）；避免副露風刻的 +1 疊加。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = [{"type": "CHI", "tiles": [_tid("1W"), _tid("2W"), _tid("3W")]}]  # 打破門清
    p["flowers"] = []
    p["hand"] = (
        [_tid("E")] * 3 + [_tid("S")] * 3 + [_tid("W")] * 3 +
        [_tid("N")] * 2 +  # 北作將
        [_tid("4D")] * 3
    )
    rewards = settle_scores_stub(env)
    assert rewards[0] == 8


def test_da_si_xi_only_16():
    """大四喜 → +16；四風皆刻（均放手牌）；避免副露風刻的 +1疊加。"""
    env = _fresh_env()
    _set_winner_basic(env, pid=0, win_source="RON")
    p = env.players[0]
    p["melds"] = [{"type": "CHI", "tiles": [_tid("1W"), _tid("2W"), _tid("3W")]}]  # 打破門清
    p["flowers"] = []
    p["hand"] = (
        [_tid("E")] * 3 + [_tid("S")] * 3 + [_tid("W")] * 3 + [_tid("N")] * 3 +
        [_tid("4D")] * 2
    )
    rewards = settle_scores_stub(env)
    assert rewards[0] == 16