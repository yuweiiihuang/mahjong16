import type { CSSProperties } from 'react'
import type { Seat } from '../../state/tableStore'
import { Tile2_5D } from './Tile2_5D'
import { TABLE_REGIONS, type Region, type RegionName } from './layout/regions'
import type { SeatView, TileView } from './types'

type OpponentHandLayerV2Props = {
  seatViews: SeatView[]
}

const HAND_COUNT = 16

const HAND_REGION_BY_SEAT: Partial<Record<Seat, RegionName>> = {
  Opponent: 'handTop',
  Left: 'handLeft',
  Right: 'handRight',
}

function regionStyle(region: Region): CSSProperties {
  return {
    left: region.x,
    top: region.y,
    width: region.width,
    height: region.height,
  }
}

function tileStyle(seat: Seat, index: number): CSSProperties {
  if (seat === 'Left' || seat === 'Right') {
    return {
      left: 40,
      top: 8 + index * 18,
      transform: 'rotate(90deg) scale(0.56)',
      zIndex: 20 + index,
    }
  }

  return {
    left: 16 + index * 30,
    top: 10,
    transform: 'scale(0.56)',
    zIndex: 20 + index,
  }
}

function compactConcealedTiles(seatView: SeatView): TileView[] {
  const hand = Array.from({ length: HAND_COUNT }, (_, index) => seatView.hand[index] ?? { label: '牌', concealed: true })
  return [...hand, seatView.drawn ?? { label: '牌', concealed: true }]
}

export function OpponentHandLayerV2({ seatViews }: OpponentHandLayerV2Props) {
  const opponents = seatViews.filter((seatView) => seatView.seat !== 'User')

  return (
    <div className="opponent-hand-layer-v2" aria-label="opponent-hand-layer-v2">
      {opponents.map((seatView) => {
        const regionName = HAND_REGION_BY_SEAT[seatView.seat]
        if (!regionName) {
          return null
        }
        const region = TABLE_REGIONS[regionName]
        const tiles = compactConcealedTiles(seatView)

        return (
          <section
            key={`${seatView.seat}-compact-hand-v2`}
            className={`opponent-hand-region-v2 opponent-hand-region-v2-${seatView.seat.toLowerCase()}`}
            aria-label={`${seatView.seat.toLowerCase()}-hand-v2`}
            data-region={regionName}
            style={regionStyle(region)}
          >
            {tiles.map((tile, index) => (
              <div
                key={`${seatView.seat}-compact-hand-${index}`}
                className="opponent-hand-tile-slot-v2"
                style={tileStyle(seatView.seat, index)}
              >
                <Tile2_5D
                  label={tile.label}
                  concealed
                  size="back"
                  ariaLabel={
                    index === HAND_COUNT
                      ? `${seatView.seat.toLowerCase()}-concealed-drawn`
                      : `${seatView.seat.toLowerCase()}-concealed-hand-${index}`
                  }
                />
              </div>
            ))}
          </section>
        )
      })}
    </div>
  )
}
