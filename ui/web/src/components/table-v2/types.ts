import type { PlayerState, Seat } from '../../state/tableStore'

export type TileSource = 'hand' | 'drawn'

export type TileView = {
  label: string
  tileId?: number
  concealed?: boolean
}

export type SeatView = {
  seat: Seat
  player: PlayerState
  active: boolean
  drawing: boolean
  hand: TileView[]
  drawn: TileView | null
  melds: TileView[][]
  flowers: TileView[]
  discards: TileView[]
}

export type SelectedTile = {
  tileId: number
  source: TileSource
}
