type Seat = 'User' | 'Opponent' | 'Right' | 'Left'

export type PlayerState = {
  id: string
  name: string
  seat: Seat
  score: number
}

export type TableState = {
  anchorId: string
  activeSeat: Seat
  drawSeat: Seat | null
  wind: 'East' | 'South' | 'West' | 'North'
  round: number
  timer: number
  players: PlayerState[]
  selfHand: string[]
  selfDiscards: string[]
  selfMelds: string[][]
  oppHand: string[]
  oppDiscards: string[]
  oppMelds: string[][]
  leftHand: string[]
  leftDiscards: string[]
  leftMelds: string[][]
  rightHand: string[]
  rightDiscards: string[]
  rightMelds: string[][]
}

export const mockTableState: TableState = {
  anchorId: 'anchor-01-self-draw',
  activeSeat: 'User',
  drawSeat: 'User',
  wind: 'East',
  round: 1,
  timer: 38,
  players: [
    { id: 'p1', name: 'You', seat: 'User', score: 9400 },
    { id: 'p2', name: 'Moka', seat: 'Right', score: 8900 },
    { id: 'p3', name: 'Leaf', seat: 'Opponent', score: 9200 },
    { id: 'p4', name: 'Space', seat: 'Left', score: 9100 },
  ],
  selfHand: ['二', '三', '四', '五', '六', '七', '八', '九', '一', '二', '三', '四', '五'],
  selfDiscards: ['九', '北', '一', '五', '三', '七', '東', '西', '南', '中', '發', '白', '二', '四', '六', '八', '三', '五'],
  selfMelds: [['二', '二', '二']],
  oppHand: Array.from({ length: 16 }, () => '牌'),
  oppDiscards: ['一', '五', '八', '東', '白', '九', '二', '六', '七', '南', '西', '發', '三', '四', '五', '北', '中', '一'],
  oppMelds: [],
  leftHand: Array.from({ length: 16 }, () => '牌'),
  leftDiscards: ['三', '七', '南', '中', '二', '六', '四', '五', '八', '九', '東', '白', '一', '三', '五', '七', '北', '發'],
  leftMelds: [],
  rightHand: Array.from({ length: 16 }, () => '牌'),
  rightDiscards: ['四', '九', '北', '發', '五', '一', '二', '三', '六', '七', '東', '南', '八', '白', '中', '一', '五', '九'],
  rightMelds: [],
}

export function resolveTableStateFromSearch(search: string): TableState {
  const params = new URLSearchParams(search)
  const anchor = params.get('anchor')

  if (!anchor || anchor === 'anchor-01-self-draw') {
    return mockTableState
  }

  return mockTableState
}
