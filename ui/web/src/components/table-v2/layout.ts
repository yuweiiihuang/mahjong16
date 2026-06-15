import type { Seat } from '../../state/tableStore'
import type { SeatView } from './types'

export const SCENE_W = 1600
export const SCENE_H = 1000

export const FELT = {
  x: 100,
  y: 95,
  width: 1400,
  height: 810,
}

export const TILE_FACE = {
  width: 54,
  height: 74,
  gap: 6,
}

export const TILE_BACK = {
  width: 42,
  height: 54,
}

export const TILE_RIVER = {
  width: 34,
  height: 44,
  gapX: 6,
  gapY: 5,
}

export const TILE_MINI = {
  width: 30,
  height: 40,
  gap: 4,
}

export const DISCARD_COLS = 6
export const DISCARD_MAX = 24

type Vec2 = {
  x: number
  y: number
}

export type TileSize = 'hand' | 'back' | 'river' | 'mini'

export type TilePose = Vec2 & {
  rotation: number
  size: TileSize
  zIndex?: number
}

type HandZone = {
  origin: Vec2
  step: Vec2
  rotation: number
  size: TileSize
  drawn: Vec2
  drawnSize?: TileSize
}

type AxisZone = {
  origin: Vec2
  right: Vec2
  up: Vec2
  rotation: number
}

type MeldFlowerZone = {
  meldOrigin: Vec2
  meldGroupStep: Vec2
  meldTileStep: Vec2
  meldRotation: number
  meldSize: TileSize
  flowerOrigin: Vec2
  flowerStep: Vec2
  flowerRotation: number
}

export const CENTER_CONSOLE_ZONE = {
  x: 660,
  y: 430,
  width: 280,
  height: 150,
}

export const HAND_ZONES: Record<Seat, HandZone> = {
  User: {
    origin: { x: 300, y: 820 },
    step: { x: 60, y: 0 },
    rotation: 0,
    size: 'hand',
    drawn: { x: 1305, y: 820 },
  },
  Opponent: {
    origin: { x: 460, y: 145 },
    step: { x: 44, y: 0 },
    rotation: 0,
    size: 'back',
    drawn: { x: 1175, y: 145 },
    drawnSize: 'back',
  },
  Left: {
    origin: { x: 295, y: 205 },
    step: { x: 0, y: 34 },
    rotation: 0,
    size: 'back',
    drawn: { x: 295, y: 760 },
    drawnSize: 'back',
  },
  Right: {
    origin: { x: 1260, y: 205 },
    step: { x: 0, y: 34 },
    rotation: 0,
    size: 'back',
    drawn: { x: 1260, y: 760 },
    drawnSize: 'back',
  },
}

export const RIVER_ZONES: Record<Seat, AxisZone> = {
  User: {
    origin: { x: 660, y: 735 },
    right: { x: TILE_RIVER.width + TILE_RIVER.gapX, y: 0 },
    up: { x: 0, y: -(TILE_RIVER.height + TILE_RIVER.gapY) },
    rotation: 0,
  },
  Opponent: {
    origin: { x: 900, y: 180 },
    right: { x: -(TILE_RIVER.width + TILE_RIVER.gapX), y: 0 },
    up: { x: 0, y: TILE_RIVER.height + TILE_RIVER.gapY },
    rotation: 180,
  },
  Left: {
    origin: { x: 345, y: 640 },
    right: { x: 0, y: -(TILE_RIVER.width + TILE_RIVER.gapX) },
    up: { x: TILE_RIVER.height + TILE_RIVER.gapY, y: 0 },
    rotation: 90,
  },
  Right: {
    origin: { x: 1210, y: 360 },
    right: { x: 0, y: TILE_RIVER.width + TILE_RIVER.gapX },
    up: { x: -(TILE_RIVER.height + TILE_RIVER.gapY), y: 0 },
    rotation: -90,
  },
}

export const MELD_FLOWER_ZONES: Record<Seat, MeldFlowerZone> = {
  User: {
    meldOrigin: { x: 420, y: 610 },
    meldGroupStep: { x: 0, y: 42 },
    meldTileStep: { x: TILE_MINI.width + TILE_MINI.gap, y: 0 },
    meldRotation: 0,
    meldSize: 'mini',
    flowerOrigin: { x: 1080, y: 735 },
    flowerStep: { x: 0, y: -(TILE_MINI.height - 10) },
    flowerRotation: 0,
  },
  Opponent: {
    meldOrigin: { x: 980, y: 235 },
    meldGroupStep: { x: 0, y: 42 },
    meldTileStep: { x: TILE_MINI.width + TILE_MINI.gap, y: 0 },
    meldRotation: 180,
    meldSize: 'mini',
    flowerOrigin: { x: 350, y: 235 },
    flowerStep: { x: 0, y: TILE_MINI.height - 10 },
    flowerRotation: 180,
  },
  Left: {
    meldOrigin: { x: 255, y: 720 },
    meldGroupStep: { x: TILE_MINI.width + 10, y: 0 },
    meldTileStep: { x: 0, y: TILE_MINI.height - 8 },
    meldRotation: 90,
    meldSize: 'mini',
    flowerOrigin: { x: 235, y: 245 },
    flowerStep: { x: 0, y: TILE_MINI.height - 12 },
    flowerRotation: 90,
  },
  Right: {
    meldOrigin: { x: 1340, y: 720 },
    meldGroupStep: { x: -(TILE_MINI.width + 10), y: 0 },
    meldTileStep: { x: 0, y: TILE_MINI.height - 8 },
    meldRotation: -90,
    meldSize: 'mini',
    flowerOrigin: { x: 1310, y: 245 },
    flowerStep: { x: 0, y: TILE_MINI.height - 12 },
    flowerRotation: -90,
  },
}

export const PLAYER_CARD_ZONES: Record<Seat, Vec2> = {
  User: { x: 260, y: 805 },
  Opponent: { x: 330, y: 52 },
  Left: { x: 50, y: 360 },
  Right: { x: 1470, y: 360 },
}

export type LayoutBoxKind =
  | 'zone'
  | 'hand'
  | 'drawn'
  | 'discard'
  | 'meld'
  | 'flower'
  | 'center-console'

export type LayoutBox = {
  id: string
  kind: LayoutBoxKind
  seat?: Seat
  zone?: string
  x: number
  y: number
  width: number
  height: number
}

export type LayoutViolation = {
  type: 'overflow' | 'overlap'
  subject: string
  target: string
}

const TILE_SIZES: Record<TileSize, { width: number; height: number }> = {
  hand: TILE_FACE,
  back: TILE_BACK,
  river: TILE_RIVER,
  mini: TILE_MINI,
}

const OWNED_ZONES: LayoutBox[] = [
  { id: 'zone-user-hand', kind: 'zone', seat: 'User', zone: 'user-hand', x: 280, y: 680, width: 1100, height: 220 },
  { id: 'zone-user-discard', kind: 'zone', seat: 'User', zone: 'user-discard', x: 640, y: 575, width: 310, height: 205 },
  { id: 'zone-user-meld-flower', kind: 'zone', seat: 'User', zone: 'user-meld-flower', x: 400, y: 515, width: 740, height: 305 },

  { id: 'zone-opponent-hand', kind: 'zone', seat: 'Opponent', zone: 'opponent-hand', x: 430, y: 120, width: 800, height: 95 },
  { id: 'zone-opponent-discard', kind: 'zone', seat: 'Opponent', zone: 'opponent-discard', x: 640, y: 170, width: 310, height: 280 },
  { id: 'zone-opponent-meld-flower', kind: 'zone', seat: 'Opponent', zone: 'opponent-meld-flower', x: 320, y: 215, width: 830, height: 270 },

  { id: 'zone-left-hand', kind: 'zone', seat: 'Left', zone: 'left-hand', x: 270, y: 180, width: 90, height: 630 },
  { id: 'zone-left-discard', kind: 'zone', seat: 'Left', zone: 'left-discard', x: 320, y: 380, width: 320, height: 310 },
  { id: 'zone-left-meld-flower', kind: 'zone', seat: 'Left', zone: 'left-meld-flower', x: 210, y: 220, width: 265, height: 610 },

  { id: 'zone-right-hand', kind: 'zone', seat: 'Right', zone: 'right-hand', x: 1235, y: 180, width: 90, height: 630 },
  { id: 'zone-right-discard', kind: 'zone', seat: 'Right', zone: 'right-discard', x: 960, y: 330, width: 320, height: 310 },
  { id: 'zone-right-meld-flower', kind: 'zone', seat: 'Right', zone: 'right-meld-flower', x: 1125, y: 220, width: 260, height: 610 },

  { id: 'zone-center-console', kind: 'center-console', zone: 'center-console', ...CENTER_CONSOLE_ZONE },
]

function boxContains(outer: LayoutBox, inner: LayoutBox): boolean {
  return (
    inner.x >= outer.x &&
    inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width &&
    inner.y + inner.height <= outer.y + outer.height
  )
}

function boxesOverlap(a: LayoutBox, b: LayoutBox): boolean {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  )
}

function tileBox(id: string, kind: LayoutBoxKind, seat: Seat, pose: TilePose): LayoutBox {
  const size = TILE_SIZES[pose.size]
  const quarterTurn = Math.abs(pose.rotation) % 180 === 90
  return {
    id,
    kind,
    seat,
    x: quarterTurn ? pose.x + (size.width - size.height) / 2 : pose.x,
    y: quarterTurn ? pose.y + (size.height - size.width) / 2 : pose.y,
    width: quarterTurn ? size.height : size.width,
    height: quarterTurn ? size.width : size.height,
  }
}

function ownerZoneFor(box: LayoutBox): LayoutBox | undefined {
  if (!box.seat || box.kind === 'zone' || box.kind === 'center-console') {
    return undefined
  }
  const seat = box.seat
  const suffix = box.kind === 'discard' ? 'discard' : box.kind === 'hand' || box.kind === 'drawn' ? 'hand' : 'meld-flower'
  return OWNED_ZONES.find((zone) => zone.seat === seat && zone.zone === `${seat.toLowerCase()}-${suffix}`)
}

export function collectLayoutBoxes(seatViews: SeatView[]): LayoutBox[] {
  const boxes = [...OWNED_ZONES]
  seatViews.forEach((seatView) => {
    if (seatView.seat === 'User') {
      seatView.hand.slice(0, 16).forEach((_, index) => {
        boxes.push(tileBox(`${seatView.seat}-hand-${index}`, 'hand', seatView.seat, getHandTilePose(seatView.seat, index)))
      })
      if (seatView.drawn) {
        boxes.push(tileBox(`${seatView.seat}-drawn`, 'drawn', seatView.seat, getDrawnTilePose(seatView.seat)))
      }
    }
    seatView.discards.slice(0, DISCARD_MAX).forEach((_, index) => {
      boxes.push(tileBox(`${seatView.seat}-discard-${index}`, 'discard', seatView.seat, getDiscardTilePose(seatView.seat, index)))
    })
    seatView.melds.forEach((meld, meldIndex) => {
      meld.forEach((_, tileIndex) => {
        boxes.push(tileBox(`${seatView.seat}-meld-${meldIndex}-${tileIndex}`, 'meld', seatView.seat, getMeldTilePose(seatView.seat, meldIndex, tileIndex)))
      })
    })
    seatView.flowers.forEach((_, index) => {
      boxes.push(tileBox(`${seatView.seat}-flower-${index}`, 'flower', seatView.seat, getFlowerTilePose(seatView.seat, index)))
    })
  })
  return boxes
}

export function findLayoutViolations(boxes: LayoutBox[]): LayoutViolation[] {
  const violations: LayoutViolation[] = []
  const contentBoxes = boxes.filter((box) => box.kind !== 'zone' && box.kind !== 'center-console')
  const centerConsole = boxes.find((box) => box.id === 'zone-center-console')

  contentBoxes.forEach((box) => {
    const owner = ownerZoneFor(box)
    if (owner && !boxContains(owner, box)) {
      violations.push({ type: 'overflow', subject: box.id, target: owner.id })
    }
    if (centerConsole && box.kind === 'discard' && boxesOverlap(box, centerConsole)) {
      violations.push({ type: 'overlap', subject: box.id, target: centerConsole.id })
    }
  })

  contentBoxes.forEach((box, index) => {
    contentBoxes.slice(index + 1).forEach((other) => {
      if (box.kind === other.kind) {
        return
      }
      if (box.seat === other.seat && boxesOverlap(box, other)) {
        violations.push({ type: 'overlap', subject: box.id, target: other.id })
      }
    })
  })

  return violations
}

function poseAt(zone: { origin: Vec2; step: Vec2; rotation: number; size: TileSize }, index: number): TilePose {
  return {
    x: zone.origin.x + zone.step.x * index,
    y: zone.origin.y + zone.step.y * index,
    rotation: zone.rotation,
    size: zone.size,
  }
}

export function getHandTilePose(seat: Seat, index: number): TilePose {
  return { ...poseAt(HAND_ZONES[seat], index), zIndex: 20 + index }
}

export function getDrawnTilePose(seat: Seat): TilePose {
  const zone = HAND_ZONES[seat]
  return {
    x: zone.drawn.x,
    y: zone.drawn.y,
    rotation: zone.rotation,
    size: zone.drawnSize ?? zone.size,
    zIndex: 45,
  }
}

export function getDiscardSlot(index: number): { col: number; row: number } {
  const cappedIndex = Math.max(0, Math.min(DISCARD_MAX - 1, index))
  return {
    col: cappedIndex % DISCARD_COLS,
    row: Math.floor(cappedIndex / DISCARD_COLS),
  }
}

export function getDiscardTilePose(seat: Seat, index: number): TilePose {
  const zone = RIVER_ZONES[seat]
  const slot = getDiscardSlot(index)
  return {
    x: zone.origin.x + zone.right.x * slot.col + zone.up.x * slot.row,
    y: zone.origin.y + zone.right.y * slot.col + zone.up.y * slot.row,
    rotation: zone.rotation,
    size: 'river',
    zIndex: 30 + index,
  }
}

export function getMeldTilePose(seat: Seat, meldIndex: number, tileIndex: number): TilePose {
  const zone = MELD_FLOWER_ZONES[seat]
  return {
    x: zone.meldOrigin.x + zone.meldGroupStep.x * meldIndex + zone.meldTileStep.x * tileIndex,
    y: zone.meldOrigin.y + zone.meldGroupStep.y * meldIndex + zone.meldTileStep.y * tileIndex,
    rotation: zone.meldRotation,
    size: zone.meldSize,
    zIndex: 35 + meldIndex,
  }
}

export function getFlowerTilePose(seat: Seat, index: number): TilePose {
  const zone = MELD_FLOWER_ZONES[seat]
  return {
    x: zone.flowerOrigin.x + zone.flowerStep.x * index,
    y: zone.flowerOrigin.y + zone.flowerStep.y * index,
    rotation: zone.flowerRotation,
    size: 'mini',
    zIndex: 34 + index,
  }
}
