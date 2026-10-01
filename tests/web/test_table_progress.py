"""Web practice tables reuse scoring, round progression, and public-only hints."""
import pytest

from app.web import WebTable
from tests.helpers.tile_pool import TilePool


@pytest.mark.parametrize('seed', [0, 1, 2])
def test_settlement_and_next_hand(seed):
    table = WebTable(seed)
    with pytest.raises(ValueError, match='尚未結束'):
        table.next_hand()
    while not table.env.done:
        table.act(table.bot.choose(table.env._obs(0)))
    result = table.snapshot()
    score = result['settlement']
    assert sum(score['payments']) == 0
    assert result['totals'] == [1000 + delta for delta in score['payments']]
    assert score['tai'] == sum(item['points'] for item in score['breakdown'])
    before = list(table.totals)
    table.settle()
    assert table.snapshot() == result  # Repeated reads/settlement cannot pay twice.
    next_dealer = table.manager.state.dealer_pid
    next_streak = table.manager.state.dealer_streak
    following = table.next_hand()
    assert following['round'] == 2
    assert following['totals'] == before
    assert following['dealer'] == next_dealer
    assert following['dealer_streak'] == next_streak
    assert following['settlement'] is None
    table.new_table()
    fresh = table.snapshot()
    assert fresh['round'] == 1
    assert fresh['totals'] == [1000] * 4
    assert fresh['quan_feng'] == 'E'
    assert fresh['dealer'] == 0


def test_round_winds_and_reseating_follow_shared_manager():
    table = WebTable(42)
    for _ in range(16):
        # Force four complete dealer rotations without modifying gameplay rules.
        table.env.done = True
        table.env.winner = (table.env.dealer_pid + 1) % 4
        table.env.win_source = 'RON'
        table.env.turn_at_win = table.env.dealer_pid
        table.settle()
        table.next_hand()
    result = table.snapshot()
    assert result['round'] == 17
    assert result['quan_feng'] == 'E'
    assert table.manager.state.jang_count == 1
    assert sorted(result['seating_order']) == [0, 1, 2, 3]
    assert result['seat_winds'][result['dealer']] == 'E'


@pytest.mark.parametrize('flower_type,source', [('ba_xian', 'TSUMO'), ('qi_qiang_yi', 'RON')])
def test_flower_wins_settle_and_reveal_flowers(flower_type, source):
    table = WebTable(42)
    env = table.env
    pool = TilePool(include_flowers=True)
    for player in env.players:
        player.flowers = []
    flowers = pool.take(range(34, 42))
    env.players[0].flowers = flowers if source == 'TSUMO' else flowers[:-1]
    if source == 'RON':
        env.players[1].flowers = flowers[-1:]
    env._resolve_flower_win(0, 1, flowers[-1], flower_type, source)
    table.advance()
    result = table.snapshot()
    assert result['winning_hand'] == flowers
    assert result['settlement']['breakdown'][0]['key'] == flower_type
    payments = result['settlement']['payments']
    assert sum(payments) == 0
    assert sum(delta < 0 for delta in payments) == (3 if source == 'TSUMO' else 1)
    table.settle()
    assert table.snapshot()['totals'] == result['totals']


def test_ting_hints_count_discard_drawn_and_public_tiles_only():
    table = WebTable(42)
    env = table.env
    pool = TilePool()
    for player in env.players:
        player.hand = []
        player.drawn = None
        player.melds = []
        player.flowers = []
        player.river = []
        player.declared_ting = False
    env.players[0].hand = pool.take([0, 1, 2, 3, 4, 5, 9, 10, 11,
                                       18, 19, 20, 27, 27, 27, 28])
    env.players[0].drawn = pool.take([29])[0]
    env.players[1].river = pool.take([28, 28, 28])
    env.wall = pool.remaining()
    env.turn = 0
    env.phase = 'TURN'
    result = table.snapshot()
    option = next(a for a in result['ting_options'] if a['from'] == 'drawn')
    assert option['tile'] == 29
    assert option['waits'] == [{'tile': 28, 'unseen': 0}]
    env.wall.reverse()
    env.players[2].hand = env.wall[:5]
    assert table.snapshot()['ting_options'] == result['ting_options']
    env.players[0].declared_ting = True
    assert table.snapshot()['ting_waits'] == [{'tile': 28, 'unseen': 0}]
    env.players[1].river.pop()
    env.players[0].drawn = 28
    assert table.snapshot()['ting_waits'] == [{'tile': 28, 'unseen': 0}]


def test_unseen_hints_ignore_opponent_concealed_kong_identity():
    table = WebTable(42)
    env = table.env
    for player in env.players:
        player.hand = []
        player.drawn = None
        player.melds = []
        player.river = []
        player.flowers = []
        player.declared_ting = False
    for hidden_tile in [0, 3]:
        pool = TilePool()
        env.players[0].hand = pool.take([1, 2, 9, 10, 11, 12, 13, 14,
                                       18, 19, 20, 21, 22, 23, 27, 27])
        env.players[0].drawn = pool.take([29])[0]
        env.players[1].melds = [{'type': 'ANGANG', 'tiles': pool.take([hidden_tile] * 4)}]
        env.wall = pool.remaining()
        env.turn = 0
        env.phase = 'TURN'
        env.players[0].declared_ting = False
        candidates = table.snapshot()['ting_options']
        option = next(a for a in candidates if a['from'] == 'drawn')
        assert option['waits'] == [{'tile': 0, 'unseen': 4}, {'tile': 3, 'unseen': 4}]
        env.players[0].declared_ting = True
        assert table.snapshot()['ting_waits'] == option['waits']
    env.players[1].melds = [{'type': 'PONG', 'tiles': [3, 3, 3]}]
    assert table.snapshot()['ting_waits'] == [
        {'tile': 0, 'unseen': 4}, {'tile': 3, 'unseen': 1}
    ]
