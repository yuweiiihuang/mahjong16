import { describe, expect, it } from 'vitest'
import { ALLOWED_REGION_OVERLAPS, REGION_NAMES, TABLE_REGIONS, getRegion } from './regions'
import { buildRegionBox } from './boxes'
import { findForbiddenOverlaps } from './validate'

describe('table-v2 region contract', () => {
  it('defines the first-pass fixed table regions without any wall space', () => {
    expect(REGION_NAMES).toHaveLength(22)
    expect(REGION_NAMES.some((name) => name.toLowerCase().includes('wall'))).toBe(false)
    expect(Object.keys(TABLE_REGIONS).some((name) => name.includes('牌牆'))).toBe(false)
  })

  it('keeps every region inside the 1600x1000 scene', () => {
    REGION_NAMES.forEach((name) => {
      const region = getRegion(name)
      expect(region.x).toBeGreaterThanOrEqual(0)
      expect(region.y).toBeGreaterThanOrEqual(0)
      expect(region.x + region.width).toBeLessThanOrEqual(1600)
      expect(region.y + region.height).toBeLessThanOrEqual(1000)
    })
  })

  it('does not overlap forbidden top-level regions outside the explicit allow-list', () => {
    const regionBoxes = REGION_NAMES.map((name) => buildRegionBox(name, TABLE_REGIONS[name]))
    const allowedPairs = ALLOWED_REGION_OVERLAPS.map(([a, b]) => [`region-${a}`, `region-${b}`] as const)

    expect(findForbiddenOverlaps(regionBoxes, allowedPairs)).toEqual([])
  })

  it('pins hand and action docks to separate bottom regions', () => {
    expect(findForbiddenOverlaps([
      buildRegionBox('handDock', TABLE_REGIONS.handDock),
      buildRegionBox('actionDock', TABLE_REGIONS.actionDock),
      buildRegionBox('riverBottom', TABLE_REGIONS.riverBottom),
    ])).toEqual([])
  })
})
