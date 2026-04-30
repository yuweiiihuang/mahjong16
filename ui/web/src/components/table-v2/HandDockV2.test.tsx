import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PlayerState } from '../../state/tableStore'
import { TABLE_REGIONS } from './layout/regions'
import { boxesOverlap } from './layout/boxes'
import { HandDockV2 } from './HandDockV2'
import type { SeatView } from './types'

function userPlayer(): PlayerState {
  return {
    id: 'user',
    name: 'You',
    seat: 'User',
    score: 1200,
  }
}

function userSeatView(): SeatView {
  return {
    seat: 'User',
    player: userPlayer(),
    active: true,
    drawing: true,
    hand: Array.from({ length: 16 }, (_, index) => ({
      label: `${index + 1}`,
      tileId: index,
    })),
    drawn: {
      label: '九筒',
      tileId: 26,
    },
    melds: [],
    flowers: [],
    discards: [],
  }
}

describe('HandDockV2', () => {
  it('renders 16 hand tiles and a separated drawn tile', () => {
    render(<HandDockV2 seatView={userSeatView()} />)

    expect(within(screen.getByLabelText('user-hand-v2')).getAllByLabelText(/^tile-/)).toHaveLength(16)
    expect(within(screen.getByLabelText('user-drawn-v2')).getByLabelText('drawn-tile-九筒')).toBeInTheDocument()
  })

  it('uses the fixed handDock region instead of a full-table rack', () => {
    render(<HandDockV2 seatView={userSeatView()} />)

    expect(screen.getByLabelText('user-hand-dock-v2')).toHaveStyle({
      left: `${TABLE_REGIONS.handDock.x}px`,
      top: `${TABLE_REGIONS.handDock.y}px`,
      width: `${TABLE_REGIONS.handDock.width}px`,
      height: `${TABLE_REGIONS.handDock.height}px`,
    })
  })

  it('marks selected hand and drawn tiles', () => {
    const { rerender } = render(<HandDockV2 seatView={userSeatView()} selectedTile={{ tileId: 0, source: 'hand' }} />)
    expect(screen.getByLabelText('tile-1-horizontal-0')).toHaveClass('is-selected')

    rerender(<HandDockV2 seatView={userSeatView()} selectedTile={{ tileId: 26, source: 'drawn' }} />)
    expect(screen.getByLabelText('drawn-tile-九筒')).toHaveClass('is-selected')
  })

  it('keeps hand and drawn click wiring compatible with session actions', () => {
    const onSelectTile = vi.fn()
    render(<HandDockV2 seatView={userSeatView()} onSelectTile={onSelectTile} />)

    fireEvent.click(screen.getByRole('button', { name: 'tile-1-horizontal-0' }))
    expect(onSelectTile).toHaveBeenCalledWith(0, 'hand')

    fireEvent.click(screen.getByRole('button', { name: 'drawn-tile-九筒' }))
    expect(onSelectTile).toHaveBeenCalledWith(26, 'drawn')
  })

  it('does not overlap riverBottom or actionDock regions', () => {
    expect(boxesOverlap(TABLE_REGIONS.handDock, TABLE_REGIONS.riverBottom)).toBe(false)
    expect(boxesOverlap(TABLE_REGIONS.handDock, TABLE_REGIONS.actionDock)).toBe(false)
  })
})
