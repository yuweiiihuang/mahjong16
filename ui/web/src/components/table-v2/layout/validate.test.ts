import { describe, expect, it } from 'vitest'
import { TABLE_REGIONS } from './regions'
import {
  buildRegionBox,
  buildRiverTileBoxes,
  buildTileBox,
  countOverlaps,
  isBoxInside,
} from './boxes'
import { findForbiddenOverlaps, validateBoxesInsideRegion, validateRegionContract } from './validate'

describe('table-v2 layout validation', () => {
  it('accepts the first region contract and rejects wall regions', () => {
    expect(validateRegionContract(TABLE_REGIONS)).toEqual([])
    expect(
      validateRegionContract({
        ...TABLE_REGIONS,
        wall: { x: 0, y: 0, width: 10, height: 10 },
      }),
    ).toEqual([
      {
        type: 'wall-region',
        subject: 'wall',
        target: 'TABLE_REGIONS',
      },
    ])
  })

  it('converts a region and tile into stable bounding boxes', () => {
    const regionBox = buildRegionBox('riverBottom', TABLE_REGIONS.riverBottom)
    const tileBox = buildTileBox('riverBottom-0', TABLE_REGIONS.riverBottom, {
      col: 0,
      row: 0,
      width: 34,
      height: 44,
      gapX: 6,
      gapY: 5,
    })

    expect(regionBox).toMatchObject({
      id: 'region-riverBottom',
      x: 610,
      y: 615,
      width: 380,
      height: 170,
    })
    expect(tileBox).toMatchObject({
      id: 'riverBottom-0',
      x: 610,
      y: 615,
      width: 34,
      height: 44,
    })
    expect(isBoxInside(regionBox, tileBox)).toBe(true)
  })

  it('keeps capped river tiles inside their owner region and reports hidden discards', () => {
    const { boxes, hiddenCount } = buildRiverTileBoxes('User', TABLE_REGIONS.riverBottom, 36)

    expect(boxes).toHaveLength(24)
    expect(hiddenCount).toBe(12)
    expect(validateBoxesInsideRegion(TABLE_REGIONS.riverBottom, boxes)).toEqual([])
  })

  it('reports overflowing tile boxes without allowing off-region overflow', () => {
    const box = buildTileBox('bad-tile', TABLE_REGIONS.handDock, {
      col: 16,
      row: 0,
      width: 54,
      height: 74,
      gapX: 6,
      gapY: 0,
    })

    expect(validateBoxesInsideRegion(TABLE_REGIONS.handDock, [box])).toEqual([
      {
        type: 'overflow',
        subject: 'bad-tile',
        target: 'handDock',
      },
    ])
  })

  it('detects forbidden overlaps between independent boxes', () => {
    const hand = buildRegionBox('handDock', TABLE_REGIONS.handDock)
    const action = buildRegionBox('actionDock', TABLE_REGIONS.actionDock)
    const shiftedAction = { ...action, x: hand.x + hand.width - 10, y: hand.y + 10 }

    expect(countOverlaps([hand, action])).toBe(0)
    expect(findForbiddenOverlaps([hand, shiftedAction])).toEqual([
      {
        type: 'overlap',
        subject: 'region-handDock',
        target: 'region-actionDock',
      },
    ])
  })
})
