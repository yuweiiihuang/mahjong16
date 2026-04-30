export type Region = {
  x: number
  y: number
  width: number
  height: number
}

export const TABLE_REGIONS = {
  playerTop: { x: 610, y: 32, width: 380, height: 78 },
  playerLeft: { x: 28, y: 420, width: 250, height: 86 },
  playerRight: { x: 1322, y: 420, width: 250, height: 86 },
  playerBottom: { x: 520, y: 900, width: 360, height: 86 },

  handTop: { x: 610, y: 112, width: 380, height: 34 },
  handLeft: { x: 28, y: 520, width: 210, height: 64 },
  handRight: { x: 1360, y: 520, width: 210, height: 64 },

  riverTop: { x: 610, y: 150, width: 380, height: 210 },
  riverLeft: { x: 330, y: 330, width: 210, height: 360 },
  riverRight: { x: 1060, y: 330, width: 210, height: 360 },
  riverBottom: { x: 610, y: 615, width: 380, height: 170 },

  meldTop: { x: 1010, y: 150, width: 260, height: 210 },
  meldLeft: { x: 255, y: 250, width: 70, height: 430 },
  meldRight: { x: 1280, y: 250, width: 70, height: 430 },
  meldBottom: { x: 300, y: 625, width: 280, height: 160 },

  flowerTop: { x: 330, y: 150, width: 230, height: 120 },
  flowerLeft: { x: 255, y: 700, width: 180, height: 80 },
  flowerRight: { x: 1165, y: 700, width: 180, height: 80 },
  flowerBottom: { x: 1010, y: 625, width: 230, height: 120 },

  center: { x: 660, y: 405, width: 280, height: 180 },
  handDock: { x: 300, y: 800, width: 1000, height: 88 },
  actionDock: { x: 900, y: 900, width: 420, height: 70 },
} as const satisfies Record<string, Region>

export type RegionName = keyof typeof TABLE_REGIONS

export const REGION_NAMES = Object.keys(TABLE_REGIONS) as RegionName[]

export const ALLOWED_REGION_OVERLAPS = [
  ['playerLeft', 'meldLeft'],
  ['playerRight', 'meldRight'],
  ['riverLeft', 'meldBottom'],
  ['riverRight', 'meldTop'],
  ['riverRight', 'flowerBottom'],
  ['meldLeft', 'meldBottom'],
  ['meldBottom', 'flowerLeft'],
  ['flowerRight', 'flowerBottom'],
] as const satisfies ReadonlyArray<readonly [RegionName, RegionName]>

export function getRegion(name: RegionName): Region {
  return TABLE_REGIONS[name]
}
