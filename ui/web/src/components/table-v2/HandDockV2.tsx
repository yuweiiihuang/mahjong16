import type { CSSProperties } from 'react'
import { Tile2_5D } from './Tile2_5D'
import { TABLE_REGIONS, type Region } from './layout/regions'
import type { SeatView, SelectedTile, TileSource, TileView } from './types'

type HandDockV2Props = {
  seatView: SeatView
  selectedTile?: SelectedTile | null
  onSelectTile?: (tileId: number, source: TileSource) => void
}

function regionStyle(region: Region): CSSProperties {
  return {
    left: region.x,
    top: region.y,
    width: region.width,
    height: region.height,
  }
}

function handTileStyle(index: number): CSSProperties {
  return {
    left: index * 55,
    top: 8,
    zIndex: 20 + index,
  }
}

function drawnTileStyle(): CSSProperties {
  return {
    right: 0,
    top: 8,
    zIndex: 45,
  }
}

function renderSelectableTile(
  tile: TileView,
  source: TileSource,
  selectedTile: SelectedTile | null | undefined,
  onSelectTile: ((tileId: number, source: TileSource) => void) | undefined,
  ariaLabel: string,
) {
  const selected = selectedTile?.source === source && selectedTile.tileId === tile.tileId
  const canSelect = typeof tile.tileId === 'number' && typeof onSelectTile === 'function'

  return (
    <Tile2_5D
      label={tile.label}
      size="hand"
      selected={selected}
      ariaLabel={ariaLabel}
      onClick={canSelect ? () => onSelectTile(tile.tileId as number, source) : undefined}
    />
  )
}

export function HandDockV2({ seatView, selectedTile, onSelectTile }: HandDockV2Props) {
  const region = TABLE_REGIONS.handDock

  return (
    <section className="hand-dock-v2" aria-label="user-hand-dock-v2" style={regionStyle(region)}>
      <div className="hand-dock-main-v2" aria-label="user-hand-v2">
        {seatView.hand.slice(0, 16).map((tile, index) => (
          <div key={`user-hand-${index}-${tile.label}`} className="hand-dock-tile-slot-v2" style={handTileStyle(index)}>
            {renderSelectableTile(
              tile,
              'hand',
              selectedTile,
              onSelectTile,
              `tile-${tile.label}-horizontal-${index}`,
            )}
          </div>
        ))}
      </div>

      {seatView.drawn ? (
        <div className="hand-dock-drawn-v2" aria-label="user-drawn-v2" style={drawnTileStyle()}>
          {renderSelectableTile(
            seatView.drawn,
            'drawn',
            selectedTile,
            onSelectTile,
            `drawn-tile-${seatView.drawn.label}`,
          )}
        </div>
      ) : null}
    </section>
  )
}
