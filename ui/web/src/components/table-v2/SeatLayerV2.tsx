import {
  SCENE_H,
  SCENE_W,
  getDrawnTilePose,
  getHandTilePose,
  type TilePose,
} from './layout'
import { Tile2_5D } from './Tile2_5D'
import type { SeatView, SelectedTile, TileSource, TileView } from './types'

type SeatLayerV2Props = {
  seatView: SeatView
  selectedTile?: SelectedTile | null
  onSelectTile?: (tileId: number, source: TileSource) => void
}

function tileSlotStyle(pose: TilePose) {
  return {
    left: pose.x,
    top: pose.y,
    transform: `rotate(${pose.rotation}deg)`,
    zIndex: pose.zIndex,
  }
}

function renderTileAt(
  tile: TileView,
  pose: TilePose,
  key: string,
  options: {
    selectedTile?: SelectedTile | null
    source?: TileSource
    onSelectTile?: (tileId: number, source: TileSource) => void
    ariaLabel?: string
  } = {},
) {
  const isClickable =
    typeof tile.tileId === 'number' && typeof options.onSelectTile === 'function' && !!options.source
  const selected =
    !!options.selectedTile &&
    options.selectedTile.source === options.source &&
    options.selectedTile.tileId === tile.tileId

  return (
    <div key={key} className="tile-pose-v2" style={tileSlotStyle(pose)}>
      <Tile2_5D
        label={tile.label}
        concealed={tile.concealed}
        size={pose.size}
        selected={selected}
        ariaLabel={options.ariaLabel ?? `tile-${tile.label}`}
        onClick={
          isClickable
            ? () => options.onSelectTile?.(tile.tileId as number, options.source as TileSource)
            : undefined
        }
      />
    </div>
  )
}

export function SeatLayerV2({ seatView, selectedTile, onSelectTile }: SeatLayerV2Props) {
  const canSelect = seatView.seat === 'User'
  const handOptions = canSelect ? { selectedTile, source: 'hand' as TileSource, onSelectTile } : {}
  const drawnOptions = canSelect ? { selectedTile, source: 'drawn' as TileSource, onSelectTile } : {}
  const renderHand = seatView.seat !== 'User'

  return (
    <div
      className={`seat-layer-v2 seat-layer-v2-${seatView.seat.toLowerCase()}`}
      aria-label={`${seatView.seat.toLowerCase()}-seat-layer-v2`}
      style={{ width: SCENE_W, height: SCENE_H }}
    >
      {renderHand ? (
        <div className="hand-rack-v2" aria-label={`${seatView.seat.toLowerCase()}-hand-v2`}>
          {seatView.hand.map((tile, index) =>
            renderTileAt(tile, getHandTilePose(seatView.seat, index), `${seatView.seat}-hand-${index}`, {
              ...handOptions,
              ariaLabel:
                seatView.seat === 'User'
                  ? `tile-${tile.label}-horizontal-${index}`
                  : `${seatView.seat.toLowerCase()}-concealed-hand-${index}`,
            }),
          )}
        </div>
      ) : null}

      {renderHand && seatView.drawn ? (
        <div className="drawn-tile-v2" aria-label={`${seatView.seat.toLowerCase()}-drawn-v2`}>
          {renderTileAt(seatView.drawn, getDrawnTilePose(seatView.seat), `${seatView.seat}-drawn`, {
            ...drawnOptions,
            ariaLabel: seatView.seat === 'User' ? `drawn-tile-${seatView.drawn.label}` : 'concealed-drawn-tile',
          })}
        </div>
      ) : null}

    </div>
  )
}
