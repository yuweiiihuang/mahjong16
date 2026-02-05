type Seat = 'User' | 'Opponent' | 'Right' | 'Left'

export type PlayerState = {
  id: string
  name: string
  seat: Seat
  score: number
}

export type TableState = {
  wind: 'East' | 'South' | 'West' | 'North'
  round: number
  timer: number
  players: PlayerState[]
  selfHand: string[]
  selfDiscards: string[]
  selfMelds: string[][]
  oppHand: string[]
  oppMelds: string[][]
  leftHand: string[]
  leftMelds: string[][]
  rightHand: string[]
  rightMelds: string[][]
}

export const mockTableState: TableState = {
  wind: 'East',
  round: 1,
  timer: 38,
  players: [
    { id: 'p1', name: 'You', seat: 'User', score: 9400 },
    { id: 'p2', name: 'Moka', seat: 'Right', score: 8900 },
    { id: 'p3', name: 'Leaf', seat: 'Opponent', score: 9200 },
    { id: 'p4', name: 'Space', seat: 'Left', score: 9100 },
  ],
  selfHand: ['中'],
  selfDiscards: ['九', '北', '一', '五', '三', '七'],
  selfMelds: [
    ['二', '二', '二'],
    ['六', '七', '八'],
    ['一', '一', '一'],
    ['三', '四', '五'],
    ['九', '九', '九'],
  ],
  oppHand: Array.from({ length: 16 }, () => '牌'),
  oppMelds: [],
  leftHand: Array.from({ length: 16 }, () => '牌'),
  leftMelds: [],
  rightHand: Array.from({ length: 16 }, () => '牌'),
  rightMelds: [],
}
