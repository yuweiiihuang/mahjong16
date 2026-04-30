import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Seat, PlayerState } from '../../state/tableStore'
import { TABLE_REGIONS } from './layout/regions'
import { buildRiverTileBoxes } from './layout/boxes'
import { RiverLayerV2 } from './RiverLayerV2'
import type { SeatView } from './types'

const SEATS: Seat[] = ['User', 'Opponent', 'Left', 'Right']

function player(seat: Seat): PlayerState {
  return {
    id: seat,
    name: seat,
    seat,
    score: 0,
  }
}

function seatView(seat: Seat, discardCount: number): SeatView {
  return {
    seat,
    player: player(seat),
    active: false,
    drawing: false,
    hand: [],
    drawn: null,
    melds: [],
    flowers: [],
    discards: Array.from({ length: discardCount }, (_, index) => ({ label: `牌${index + 1}` })),
  }
}

function seatViews(discardCount: number): SeatView[] {
  return SEATS.map((seat) => seatView(seat, discardCount))
}

describe('RiverLayerV2', () => {
  it.each([0, 1, 6, 12, 18, 24, 36])('caps each river at 24 visible tiles for %i discards', (count) => {
    render(<RiverLayerV2 seatViews={seatViews(count)} />)

    SEATS.forEach((seat) => {
      const grid = screen.getByLabelText(`${seat.toLowerCase()}-discard-grid-v2`)
      expect(within(grid).queryAllByLabelText(/^tile-/)).toHaveLength(Math.min(count, 24))
    })
  })

  it('shows overflow badges instead of rendering off-region tiles', () => {
    render(<RiverLayerV2 seatViews={seatViews(36)} />)

    SEATS.forEach((seat) => {
      expect(screen.getByLabelText(`${seat.toLowerCase()}-discard-overflow-v2`)).toHaveTextContent('+12')
    })
  })

  it('renders all four river labels', () => {
    render(<RiverLayerV2 seatViews={seatViews(1)} />)

    expect(screen.getByText('自己牌河')).toBeInTheDocument()
    expect(screen.getByText('對家牌河')).toBeInTheDocument()
    expect(screen.getByText('上家牌河')).toBeInTheDocument()
    expect(screen.getByText('下家牌河')).toBeInTheDocument()
  })

  it('uses region-sized grids instead of full-table discard canvases', () => {
    render(<RiverLayerV2 seatViews={seatViews(1)} />)

    const bottomGrid = screen.getByLabelText('user-discard-grid-v2')
    expect(bottomGrid).toHaveStyle({
      left: `${TABLE_REGIONS.riverBottom.x}px`,
      top: `${TABLE_REGIONS.riverBottom.y}px`,
      width: `${TABLE_REGIONS.riverBottom.width}px`,
      height: `${TABLE_REGIONS.riverBottom.height}px`,
    })
  })

  it('keeps 36-discard river boxes inside their owner regions', () => {
    expect(buildRiverTileBoxes('User', TABLE_REGIONS.riverBottom, 36).hiddenCount).toBe(12)
    expect(buildRiverTileBoxes('User', TABLE_REGIONS.riverBottom, 36).boxes).toHaveLength(24)
  })
})
