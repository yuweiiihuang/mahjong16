import { DISCARD_MAX, SCENE_H, SCENE_W, getDiscardTilePose } from './layout'
import { Tile2_5D } from './Tile2_5D'
import type { SeatView } from './types'

type DiscardGridV2Props = {
  seatView: SeatView
}

export function DiscardGridV2({ seatView }: DiscardGridV2Props) {
  const labels = seatView.discards.slice(0, DISCARD_MAX)

  return (
    <div
      className="discard-grid-v2"
      aria-label={`${seatView.seat.toLowerCase()}-discard-grid-v2`}
      style={{
        width: SCENE_W,
        height: SCENE_H,
      }}
    >
      {labels.map((tile, index) => {
        const pose = getDiscardTilePose(seatView.seat, index)
        return (
          <div
            key={`${seatView.seat}-discard-${index}-${tile.label}`}
            className="tile-pose-v2 discard-slot-v2"
            style={{
              left: pose.x,
              top: pose.y,
              transform: `rotate(${pose.rotation}deg)`,
              zIndex: pose.zIndex,
            }}
          >
            <Tile2_5D label={tile.label} size={pose.size} />
          </div>
        )
      })}
    </div>
  )
}
