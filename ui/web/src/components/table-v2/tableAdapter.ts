import type { PlayerState, Seat, TableState } from '../../state/tableStore'
import type { SeatView, TileView } from './types'

const SEAT_LABELS: Record<Seat, string> = {
  User: '自己',
  Opponent: '對家',
  Left: '上家',
  Right: '下家',
}

function fallbackPlayer(seat: Seat): PlayerState {
  return {
    id: `fallback-${seat}`,
    name: SEAT_LABELS[seat],
    seat,
    score: 0,
  }
}

function getPlayer(table: TableState, seat: Seat): PlayerState {
  return table.players.find((player) => player.seat === seat) ?? fallbackPlayer(seat)
}

function tiles(labels: string[], tileIds?: Array<number | undefined>, concealed = false): TileView[] {
  return labels.map((label, index) => ({
    label,
    tileId: tileIds?.[index],
    concealed,
  }))
}

function melds(groups: string[][]): TileView[][] {
  return groups.map((group) => tiles(group))
}

export function tableStateToSeatViews(table: TableState): SeatView[] {
  return [
    {
      seat: 'User',
      player: getPlayer(table, 'User'),
      active: table.activeSeat === 'User',
      drawing: table.drawSeat === 'User',
      hand: tiles(table.selfHand, table.selfHandTileIds),
      drawn: table.selfDrawn ? { label: table.selfDrawn, tileId: table.selfDrawnTileId ?? undefined } : null,
      melds: melds(table.selfMelds),
      flowers: tiles(table.selfFlowers),
      discards: tiles(table.selfDiscards),
    },
    {
      seat: 'Opponent',
      player: getPlayer(table, 'Opponent'),
      active: table.activeSeat === 'Opponent',
      drawing: table.drawSeat === 'Opponent',
      hand: tiles(table.oppHand, undefined, true),
      drawn: table.drawSeat === 'Opponent' ? { label: '牌', concealed: true } : null,
      melds: melds(table.oppMelds),
      flowers: tiles(table.oppFlowers),
      discards: tiles(table.oppDiscards),
    },
    {
      seat: 'Left',
      player: getPlayer(table, 'Left'),
      active: table.activeSeat === 'Left',
      drawing: table.drawSeat === 'Left',
      hand: tiles(table.leftHand, undefined, true),
      drawn: table.drawSeat === 'Left' ? { label: '牌', concealed: true } : null,
      melds: melds(table.leftMelds),
      flowers: tiles(table.leftFlowers),
      discards: tiles(table.leftDiscards),
    },
    {
      seat: 'Right',
      player: getPlayer(table, 'Right'),
      active: table.activeSeat === 'Right',
      drawing: table.drawSeat === 'Right',
      hand: tiles(table.rightHand, undefined, true),
      drawn: table.drawSeat === 'Right' ? { label: '牌', concealed: true } : null,
      melds: melds(table.rightMelds),
      flowers: tiles(table.rightFlowers),
      discards: tiles(table.rightDiscards),
    },
  ]
}
