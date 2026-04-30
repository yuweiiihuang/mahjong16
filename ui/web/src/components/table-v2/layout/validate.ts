import { boxesOverlap, buildRegionBox, isBoxInside, type LayoutBox } from './boxes'
import { ALLOWED_REGION_OVERLAPS, REGION_NAMES, TABLE_REGIONS, type Region, type RegionName } from './regions'

export type LayoutViolation = {
  type: 'overflow' | 'overlap' | 'wall-region'
  subject: string
  target: string
}

export function validateRegionContract(regions: Record<string, Region>): LayoutViolation[] {
  const violations: LayoutViolation[] = []

  Object.keys(regions).forEach((name) => {
    if (name.toLowerCase().includes('wall') || name.includes('牌牆')) {
      violations.push({
        type: 'wall-region',
        subject: name,
        target: 'TABLE_REGIONS',
      })
    }
  })

  findForbiddenOverlaps(
    Object.entries(regions)
      .filter(([name]) => REGION_NAMES.includes(name as RegionName))
      .map(([name, region]) => buildRegionBox(name as RegionName, region)),
    allowedRegionBoxPairs(),
  ).forEach((violation) => violations.push(violation))

  return violations
}

export function validateBoxesInsideRegion(region: Region, boxes: LayoutBox[]): LayoutViolation[] {
  const target = regionNameFor(region)
  return boxes
    .filter((box) => !isBoxInside(region, box))
    .map((box) => ({
      type: 'overflow' as const,
      subject: box.id,
      target,
    }))
}

export function findForbiddenOverlaps(
  boxes: LayoutBox[],
  allowedPairs: ReadonlyArray<readonly [string, string]> = [],
): LayoutViolation[] {
  const violations: LayoutViolation[] = []

  boxes.forEach((box, index) => {
    boxes.slice(index + 1).forEach((other) => {
      if (boxesOverlap(box, other) && !isAllowedPair(box.id, other.id, allowedPairs)) {
        violations.push({
          type: 'overlap',
          subject: box.id,
          target: other.id,
        })
      }
    })
  })

  return violations
}

function regionNameFor(region: Region): string {
  const match = REGION_NAMES.find((name) => {
    const candidate = TABLE_REGIONS[name]
    return (
      candidate.x === region.x &&
      candidate.y === region.y &&
      candidate.width === region.width &&
      candidate.height === region.height
    )
  })

  return match ?? 'region'
}

function allowedRegionBoxPairs(): ReadonlyArray<readonly [string, string]> {
  return ALLOWED_REGION_OVERLAPS.map(([a, b]) => [`region-${a}`, `region-${b}`] as const)
}

function isAllowedPair(
  subject: string,
  target: string,
  allowedPairs: ReadonlyArray<readonly [string, string]>,
): boolean {
  return allowedPairs.some(
    ([a, b]) => (a === subject && b === target) || (a === target && b === subject),
  )
}
