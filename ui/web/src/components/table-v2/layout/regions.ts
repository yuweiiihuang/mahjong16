export type Region = {
  x: number
  y: number
  width: number
  height: number
}

export const TABLE_REGIONS = {
  playerTop: { x: 330, y: 52, width: 110, height: 120 },
  playerLeft: { x: 50, y: 360, width: 100, height: 130 },
  playerRight: { x: 1470, y: 360, width: 100, height: 130 },
  playerBottom: { x: 260, y: 805, width: 110, height: 120 },

  handTop: { x: 470, y: 58, width: 620, height: 78 },
  handLeft: { x: 175, y: 315, width: 130, height: 325 },
  handRight: { x: 1305, y: 245, width: 120, height: 335 },

  riverTop: { x: 470, y: 155, width: 500, height: 70 },
  riverLeft: { x: 350, y: 325, width: 90, height: 315 },
  riverRight: { x: 1195, y: 245, width: 80, height: 335 },
  riverBottom: { x: 635, y: 625, width: 490, height: 75 },

  meldTop: { x: 1110, y: 52, width: 120, height: 120 },
  meldLeft: { x: 175, y: 225, width: 130, height: 85 },
  meldRight: { x: 1305, y: 585, width: 120, height: 90 },
  meldBottom: { x: 380, y: 790, width: 130, height: 90 },

  flowerTop: { x: 985, y: 155, width: 100, height: 70 },
  flowerLeft: { x: 350, y: 225, width: 90, height: 85 },
  flowerRight: { x: 1195, y: 585, width: 90, height: 70 },
  flowerBottom: { x: 520, y: 625, width: 95, height: 75 },

  center: { x: 620, y: 345, width: 430, height: 190 },
  handDock: { x: 530, y: 785, width: 650, height: 105 },
  actionDock: { x: 600, y: 720, width: 480, height: 55 },
} as const satisfies Record<string, Region>

export type RegionName = keyof typeof TABLE_REGIONS

export const REGION_NAMES = Object.keys(TABLE_REGIONS) as RegionName[]

export const ALLOWED_REGION_OVERLAPS: ReadonlyArray<readonly [RegionName, RegionName]> = []

export function getRegion(name: RegionName): Region {
  return TABLE_REGIONS[name]
}
