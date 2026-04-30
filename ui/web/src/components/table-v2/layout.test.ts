import { describe, expect, it } from 'vitest'
import {
  CENTER_CONSOLE_ZONE,
  DISCARD_MAX,
  FELT,
  PLAYER_CARD_ZONES,
  collectLayoutBoxes,
  findLayoutViolations,
  getDiscardSlot,
  getDiscardTilePose,
} from './layout'
import type { Seat } from '../../state/tableStore'
import { resolveTableStateFromSearch } from '../../state/tableStore'
import { tableStateToSeatViews } from './tableAdapter'

describe('table-v2 layout', () => {
  it('maps discard indexes into stable 6x6 slots', () => {
    expect(getDiscardSlot(0)).toMatchObject({ col: 0, row: 0 })
    expect(getDiscardSlot(1)).toMatchObject({ col: 1, row: 0 })
    expect(getDiscardSlot(5)).toMatchObject({ col: 5, row: 0 })
    expect(getDiscardSlot(6)).toMatchObject({ col: 0, row: 1 })
    expect(getDiscardSlot(23)).toMatchObject({ col: 5, row: 3 })
    expect(getDiscardSlot(999)).toMatchObject(getDiscardSlot(DISCARD_MAX - 1))
  })

  it('keeps user and opponent discard growth mirrored', () => {
    const user0 = getDiscardTilePose('User', 0)
    const user1 = getDiscardTilePose('User', 1)
    const user6 = getDiscardTilePose('User', 6)
    expect(user1.x).toBeGreaterThan(user0.x)
    expect(user1.y).toBe(user0.y)
    expect(user6.y).toBeLessThan(user0.y)

    const opp0 = getDiscardTilePose('Opponent', 0)
    const opp1 = getDiscardTilePose('Opponent', 1)
    const opp6 = getDiscardTilePose('Opponent', 6)
    expect(opp1.x).toBeLessThan(opp0.x)
    expect(opp1.y).toBe(opp0.y)
    expect(opp6.y).toBeGreaterThan(opp0.y)
  })

  it('keeps side discard growth vertical-first from each seat perspective', () => {
    const left0 = getDiscardTilePose('Left', 0)
    const left1 = getDiscardTilePose('Left', 1)
    const left6 = getDiscardTilePose('Left', 6)
    expect(left1.y).toBeLessThan(left0.y)
    expect(left6.x).toBeGreaterThan(left0.x)

    const right0 = getDiscardTilePose('Right', 0)
    const right1 = getDiscardTilePose('Right', 1)
    const right6 = getDiscardTilePose('Right', 6)
    expect(right1.y).toBeGreaterThan(right0.y)
    expect(right6.x).toBeLessThan(right0.x)
  })

  it('reserves player-card gutter outside felt and away from center console', () => {
    ;(['Left', 'Right'] as Seat[]).forEach((seat) => {
      const zone = PLAYER_CARD_ZONES[seat]
      if (seat === 'Left') {
        expect(zone.x).toBeLessThan(FELT.x)
      } else {
        expect(zone.x).toBeGreaterThan(FELT.x + FELT.width - 200)
      }
    })

    expect(PLAYER_CARD_ZONES.Opponent.y).toBeLessThan(FELT.y)
    expect(PLAYER_CARD_ZONES.User.y).toBeGreaterThan(FELT.y + FELT.height - 20)
    expect(CENTER_CONSOLE_ZONE.x).toBeGreaterThan(FELT.x + 400)
    expect(CENTER_CONSOLE_ZONE.x + CENTER_CONSOLE_ZONE.width).toBeLessThan(FELT.x + FELT.width - 400)
  })

  it('keeps stress-anchor table elements inside owned zones without forbidden overlaps', () => {
    const table = resolveTableStateFromSearch('?anchor=anchor-v2-stress')
    const boxes = collectLayoutBoxes(tableStateToSeatViews(table))
    const violations = findLayoutViolations(boxes)
    expect(violations).toEqual([])
  })
})
