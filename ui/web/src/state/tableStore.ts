export type Seat = 'User' | 'Opponent' | 'Right' | 'Left'

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
  selfFlowers: string[]
  selfMelds: string[][]
  oppHand: string[]
  oppDiscards: string[]
  oppFlowers: string[]
  oppMelds: string[][]
  leftHand: string[]
  leftDiscards: string[]
  leftFlowers: string[]
  leftMelds: string[][]
  rightHand: string[]
  rightDiscards: string[]
  rightFlowers: string[]
  rightMelds: string[][]
}

export const mockTableState: TableState = {
  anchorId: 'anchor-01-self-draw',
  activeSeat: 'User',
  drawSeat: 'User',
  wind: 'East',
  round: 4,
  timer: 5,
  players: [
    { id: 'p1', name: 'You', seat: 'User', score: 1200 },
    { id: 'p2', name: 'Moka', seat: 'Right', score: 20800 },
    { id: 'p3', name: 'Leaf', seat: 'Opponent', score: 37600 },
    { id: 'p4', name: 'Space', seat: 'Left', score: 40400 },
  ],
  selfHand: ['一', '二', '三', '四', '五', '六', '七', '八', '九', '一'],
  selfDiscards: ['九', '北', '一', '五', '三', '七', '東', '西', '南', '中', '發', '白', '二', '四', '六', '八', '三', '五', '南', '白', '東'],
  selfFlowers: ['1', '2', '3', '4', '5', '6', '7', '8'],
  selfMelds: [['二', '二', '二'], ['三', '四', '五']],
  oppHand: Array.from({ length: 10 }, () => '牌'),
  oppDiscards: ['一', '五', '八', '東', '白', '九', '二', '六', '七', '南', '西', '發', '三', '四', '五', '北', '中', '一', '二', '六', '八'],
  oppFlowers: ['1', '2', '3', '4', '5', '6', '7', '8'],
  oppMelds: [['二', '三', '四'], ['五', '六', '七']],
  leftHand: Array.from({ length: 10 }, () => '牌'),
  leftDiscards: ['三', '七', '南', '中', '二', '六', '四', '五', '八', '九', '東', '白', '一', '三', '五', '七', '北', '發', '西', '四', '六'],
  leftFlowers: ['1', '2', '3', '4', '5', '6', '7', '8'],
  leftMelds: [['一', '一', '一'], ['七', '八', '九']],
  rightHand: Array.from({ length: 10 }, () => '牌'),
  rightDiscards: ['四', '九', '北', '發', '五', '一', '二', '三', '六', '七', '東', '南', '八', '白', '中', '一', '五', '九', '西', '二', '六'],
  rightFlowers: ['1', '2', '3', '4', '5', '6', '7', '8'],
  rightMelds: [['四', '四', '四'], ['六', '七', '八']],
}

const DEFAULT_ANCHOR_ID = 'anchor-01-self-draw'

const LEFT_MELD_SETS: string[][] = [
  ['一', '一', '一'],
  ['七', '八', '九'],
  ['中', '中', '中'],
  ['三', '四', '五'],
  ['北', '北', '北'],
]

function createLeftMeldFixture(meldCount: number): TableState {
  const cappedMeldCount = Math.max(0, Math.min(5, meldCount))
  const handCount = 16 - cappedMeldCount * 3
  return {
    ...mockTableState,
    anchorId: `anchor-left-meld-${cappedMeldCount}`,
    leftMelds: LEFT_MELD_SETS.slice(0, cappedMeldCount),
    leftHand: Array.from({ length: handCount }, () => '牌'),
  }
}

const leftMeldFixtures: Record<string, TableState> = Object.fromEntries(
  Array.from({ length: 6 }, (_, idx) => {
    const fixture = createLeftMeldFixture(idx)
    return [fixture.anchorId, fixture]
  }),
) as Record<string, TableState>

const anchorFixtures: Record<string, TableState> = {
  [DEFAULT_ANCHOR_ID]: mockTableState,
  ...leftMeldFixtures,
}

export function resolveTableStateFromSearch(search: string): TableState {
  const params = new URLSearchParams(search)
  const anchor = params.get('anchor') ?? DEFAULT_ANCHOR_ID
  const fixture = anchorFixtures[anchor]
  if (fixture) {
    return fixture
  }

  console.warn(
    `[tableStore] Unknown anchor "${anchor}", falling back to "${DEFAULT_ANCHOR_ID}"`,
  )
  return anchorFixtures[DEFAULT_ANCHOR_ID]
}
