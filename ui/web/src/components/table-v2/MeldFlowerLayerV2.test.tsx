import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PlayerState, Seat } from '../../state/tableStore'
import { TABLE_REGIONS } from './layout/regions'
import { MeldFlowerLayerV2 } from './MeldFlowerLayerV2'
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

function seatView(seat: Seat, meldCount: number, flowerCount: number): SeatView {
  return {
    seat,
    player: player(seat),
    active: false,
    drawing: false,
    hand: [],
    drawn: null,
    melds: Array.from({ length: meldCount }, (_, groupIndex) =>
      Array.from({ length: 3 }, (_, tileIndex) => ({ label: `副${groupIndex + 1}-${tileIndex + 1}` })),
    ),
    flowers: Array.from({ length: flowerCount }, (_, index) => ({ label: `花${index + 1}` })),
    discards: [],
  }
}

function seatViews(meldCount: number, flowerCount: number): SeatView[] {
  return SEATS.map((seat) => seatView(seat, meldCount, flowerCount))
}

describe('MeldFlowerLayerV2', () => {
  it.each([0, 1, 2, 3, 4, 5])('renders %i meld groups per seat inside meld regions', (meldCount) => {
    render(<MeldFlowerLayerV2 seatViews={seatViews(meldCount, 0)} />)

    SEATS.forEach((seat) => {
      const rack = screen.getByLabelText(`${seat.toLowerCase()}-melds-v2`)
      expect(within(rack).queryAllByLabelText(/^tile-/)).toHaveLength(meldCount * 3)
      expect(rack.querySelectorAll('.meld-group-v2')).toHaveLength(meldCount)
    })
  })

  it.each([0, 1, 4, 8])('renders %i flowers per seat inside flower regions', (flowerCount) => {
    render(<MeldFlowerLayerV2 seatViews={seatViews(0, flowerCount)} />)

    SEATS.forEach((seat) => {
      const rack = screen.getByLabelText(`${seat.toLowerCase()}-flowers-v2`)
      expect(within(rack).queryAllByLabelText(/^tile-/)).toHaveLength(flowerCount)
    })
  })

  it('uses fixed meld and flower regions instead of full-table racks', () => {
    render(<MeldFlowerLayerV2 seatViews={seatViews(1, 1)} />)

    expect(screen.getByLabelText('user-melds-v2')).toHaveStyle({
      left: `${TABLE_REGIONS.meldBottom.x}px`,
      top: `${TABLE_REGIONS.meldBottom.y}px`,
      width: `${TABLE_REGIONS.meldBottom.width}px`,
      height: `${TABLE_REGIONS.meldBottom.height}px`,
    })
    expect(screen.getByLabelText('user-flowers-v2')).toHaveStyle({
      left: `${TABLE_REGIONS.flowerBottom.x}px`,
      top: `${TABLE_REGIONS.flowerBottom.y}px`,
      width: `${TABLE_REGIONS.flowerBottom.width}px`,
      height: `${TABLE_REGIONS.flowerBottom.height}px`,
    })
  })

  it('keeps meld and flower labels separate for all seats', () => {
    render(<MeldFlowerLayerV2 seatViews={seatViews(1, 1)} />)

    expect(screen.getByText('自己副露')).toBeInTheDocument()
    expect(screen.getByText('對家副露')).toBeInTheDocument()
    expect(screen.getByText('上家副露')).toBeInTheDocument()
    expect(screen.getByText('下家副露')).toBeInTheDocument()
    expect(screen.getByText('自己花牌')).toBeInTheDocument()
    expect(screen.getByText('對家花牌')).toBeInTheDocument()
    expect(screen.getByText('上家花牌')).toBeInTheDocument()
    expect(screen.getByText('下家花牌')).toBeInTheDocument()
  })
})
