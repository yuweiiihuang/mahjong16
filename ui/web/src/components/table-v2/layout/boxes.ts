import type { Seat } from '../../../state/tableStore'
import type { Region, RegionName } from './regions'

export type LayoutBox = {
  id: string
  x: number
  y: number
  width: number
  height: number
}

export type TileGridSpec = {
  col: number
  row: number
  width: number
  height: number
  gapX: number
  gapY: number
}

const RIVER_COLS = 6
const RIVER_MAX_VISIBLE = 24
const RIVER_TILE = {
  width: 34,
  height: 38,
  gapX: 6,
  gapY: 5,
}

export function buildRegionBox(name: RegionName, region: Region): LayoutBox {
  return {
    id: `region-${name}`,
    ...region,
  }
}

export function buildTileBox(id: string, region: Region, spec: TileGridSpec): LayoutBox {
  return {
    id,
    x: region.x + spec.col * (spec.width + spec.gapX),
    y: region.y + spec.row * (spec.height + spec.gapY),
    width: spec.width,
    height: spec.height,
  }
}

export function buildRiverTileBoxes(
  seat: Seat,
  region: Region,
  discardCount: number,
): { boxes: LayoutBox[]; hiddenCount: number } {
  const visibleCount = Math.min(Math.max(discardCount, 0), RIVER_MAX_VISIBLE)
  const boxes = Array.from({ length: visibleCount }, (_, index) =>
    buildTileBox(`${seat}-river-${index}`, region, {
      col: index % RIVER_COLS,
      row: Math.floor(index / RIVER_COLS),
      ...RIVER_TILE,
    }),
  )

  return {
    boxes,
    hiddenCount: Math.max(discardCount - RIVER_MAX_VISIBLE, 0),
  }
}

export function isBoxInside(outer: LayoutBox | Region, inner: LayoutBox): boolean {
  return (
    inner.x >= outer.x &&
    inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width &&
    inner.y + inner.height <= outer.y + outer.height
  )
}

export function boxesOverlap(a: LayoutBox | Region, b: LayoutBox | Region): boolean {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  )
}

export function countOverlaps(boxes: LayoutBox[]): number {
  let count = 0
  boxes.forEach((box, index) => {
    boxes.slice(index + 1).forEach((other) => {
      if (boxesOverlap(box, other)) {
        count += 1
      }
    })
  })
  return count
}
