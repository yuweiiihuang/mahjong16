import type { CSSProperties } from 'react'
import type { Seat } from '../../state/tableStore'
import { Tile2_5D } from './Tile2_5D'
import { buildRiverTileBoxes } from './layout/boxes'
import { TABLE_REGIONS, type Region, type RegionName } from './layout/regions'
import type { SeatView } from './types'

type RiverLayerV2Props = {
  seatViews: SeatView[]
}

const DISCARD_MAX = 24

const SEAT_LABELS: Record<Seat, string> = {
  User: '自己',
  Opponent: '對家',
  Left: '上家',
  Right: '下家',
}

const RIVER_REGION_BY_SEAT: Record<Seat, RegionName> = {
  User: 'riverBottom',
  Opponent: 'riverTop',
  Left: 'riverLeft',
  Right: 'riverRight',
}

const RIVER_ROTATION_BY_SEAT: Record<Seat, number> = {
  User: 0,
  Opponent: 180,
  Left: 90,
  Right: -90,
}

function regionStyle(region: Region): CSSProperties {
  return {
    left: region.x,
    top: region.y,
    width: region.width,
    height: region.height,
  }
}

function tileStyle(region: Region, box: { x: number; y: number }, rotation: number): CSSProperties {
  return {
    left: box.x - region.x,
    top: box.y - region.y,
    transform: `rotate(${rotation}deg) scale(0.9)`,
  }
}

export function RiverLayerV2({ seatViews }: RiverLayerV2Props) {
  return (
    <div className="river-layer-v2" aria-label="river-layer-v2">
      {seatViews.map((seatView) => {
        const regionName = RIVER_REGION_BY_SEAT[seatView.seat]
        const region = TABLE_REGIONS[regionName]
        const visibleTiles = seatView.discards.slice(0, DISCARD_MAX)
        const { boxes, hiddenCount } = buildRiverTileBoxes(seatView.seat, region, seatView.discards.length)
        const rotation = RIVER_ROTATION_BY_SEAT[seatView.seat]

        return (
          <section
            key={`${seatView.seat}-river-v2`}
            className={`river-region-v2 river-region-v2-${seatView.seat.toLowerCase()}`}
            aria-label={`${seatView.seat.toLowerCase()}-discard-grid-v2`}
            data-region={regionName}
            style={regionStyle(region)}
          >
            <div className={`river-label-v2 river-label-v2-${seatView.seat.toLowerCase()}`}>
              {SEAT_LABELS[seatView.seat]}牌河
            </div>

            {visibleTiles.map((tile, index) => {
              const box = boxes[index]
              return (
                <div
                  key={`${seatView.seat}-river-${index}-${tile.label}`}
                  className="river-tile-slot-v2"
                  style={tileStyle(region, box, rotation)}
                >
                  <Tile2_5D label={tile.label} size="river" ariaLabel={`tile-${tile.label}-${index}`} />
                </div>
              )
            })}

            {hiddenCount > 0 ? (
              <div className="river-overflow-badge-v2" aria-label={`${seatView.seat.toLowerCase()}-discard-overflow-v2`}>
                +{hiddenCount}
              </div>
            ) : null}
          </section>
        )
      })}
    </div>
  )
}
