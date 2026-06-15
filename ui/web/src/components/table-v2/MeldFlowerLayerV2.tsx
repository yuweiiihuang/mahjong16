import type { CSSProperties } from 'react'
import type { Seat } from '../../state/tableStore'
import { Tile2_5D } from './Tile2_5D'
import { TABLE_REGIONS, type Region, type RegionName } from './layout/regions'
import type { SeatView } from './types'

type MeldFlowerLayerV2Props = {
  seatViews: SeatView[]
}

const SEAT_LABELS: Record<Seat, string> = {
  User: '自己',
  Opponent: '對家',
  Left: '上家',
  Right: '下家',
}

const MELD_REGION_BY_SEAT: Record<Seat, RegionName> = {
  User: 'meldBottom',
  Opponent: 'meldTop',
  Left: 'meldLeft',
  Right: 'meldRight',
}

const FLOWER_REGION_BY_SEAT: Record<Seat, RegionName> = {
  User: 'flowerBottom',
  Opponent: 'flowerTop',
  Left: 'flowerLeft',
  Right: 'flowerRight',
}

const ROTATION_BY_SEAT: Record<Seat, number> = {
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

function meldGroupStyle(seat: Seat, index: number): CSSProperties {
  if (seat === 'Left' || seat === 'Right') {
    return {
      left: 8 + (index % 2) * 58,
      top: 28 + Math.floor(index / 2) * 20,
    }
  }

  return {
    left: 8 + (index % 2) * 58,
    top: 28 + Math.floor(index / 2) * 24,
  }
}

function meldTileStyle(seat: Seat, tileIndex: number): CSSProperties {
  const rotation = ROTATION_BY_SEAT[seat]
  if (seat === 'Left' || seat === 'Right') {
    return {
      left: tileIndex * 16,
      top: 0,
      transform: `rotate(${rotation}deg) scale(0.64)`,
    }
  }

  return {
    left: tileIndex * 16,
    top: 0,
    transform: `rotate(${rotation}deg) scale(0.64)`,
  }
}

function flowerTileStyle(seat: Seat, index: number): CSSProperties {
  const rotation = ROTATION_BY_SEAT[seat]
  return {
    left: 4 + index * 11,
    top: seat === 'User' || seat === 'Opponent' ? 36 : 34,
    transform: `rotate(${rotation}deg) scale(0.48)`,
  }
}

export function MeldFlowerLayerV2({ seatViews }: MeldFlowerLayerV2Props) {
  return (
    <div className="meld-flower-layer-v2" aria-label="meld-flower-layer-v2">
      {seatViews.map((seatView) => {
        const meldRegionName = MELD_REGION_BY_SEAT[seatView.seat]
        const flowerRegionName = FLOWER_REGION_BY_SEAT[seatView.seat]
        const meldRegion = TABLE_REGIONS[meldRegionName]
        const flowerRegion = TABLE_REGIONS[flowerRegionName]

        return (
          <div key={`${seatView.seat}-meld-flower-v2`}>
            <section
              className={`meld-region-v2 meld-region-v2-${seatView.seat.toLowerCase()}`}
              aria-label={`${seatView.seat.toLowerCase()}-melds-v2`}
              data-region={meldRegionName}
              style={regionStyle(meldRegion)}
            >
              <div className="meld-flower-label-v2">{SEAT_LABELS[seatView.seat]}副露</div>
              {seatView.melds.slice(0, 5).map((meld, meldIndex) => (
                <div
                  key={`${seatView.seat}-meld-group-${meldIndex}`}
                  className="meld-group-v2"
                  style={meldGroupStyle(seatView.seat, meldIndex)}
                >
                  {meld.map((tile, tileIndex) => (
                    <div
                      key={`${seatView.seat}-meld-${meldIndex}-${tileIndex}-${tile.label}`}
                      className="meld-flower-tile-slot-v2"
                      style={meldTileStyle(seatView.seat, tileIndex)}
                    >
                      <Tile2_5D label={tile.label} size="mini" ariaLabel={`tile-${tile.label}`} />
                    </div>
                  ))}
                </div>
              ))}
            </section>

            <section
              className={`flower-region-v2 flower-region-v2-${seatView.seat.toLowerCase()}`}
              aria-label={`${seatView.seat.toLowerCase()}-flowers-v2`}
              data-region={flowerRegionName}
              style={regionStyle(flowerRegion)}
            >
              <div className="meld-flower-label-v2">{SEAT_LABELS[seatView.seat]}花牌</div>
              {seatView.flowers.slice(0, 8).map((tile, index) => (
                <div
                  key={`${seatView.seat}-flower-${index}-${tile.label}`}
                  className="meld-flower-tile-slot-v2"
                  style={flowerTileStyle(seatView.seat, index)}
                >
                  <Tile2_5D label={tile.label} size="mini" ariaLabel={`tile-${tile.label}`} />
                </div>
              ))}
            </section>
          </div>
        )
      })}
    </div>
  )
}
