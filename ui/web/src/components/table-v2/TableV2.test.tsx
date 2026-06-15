import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { mockTableState, resolveTableStateFromSearch } from '../../state/tableStore'
import { TableV2 } from './TableV2'
import { tableStateToSeatViews } from './tableAdapter'

describe('TableV2', () => {
  it('adapts existing table state into four seat views', () => {
    const seats = tableStateToSeatViews(mockTableState)
    expect(seats).toHaveLength(4)
    expect(seats.find((seat) => seat.seat === 'User')?.hand).toHaveLength(mockTableState.selfHand.length)
    expect(seats.find((seat) => seat.seat === 'Opponent')?.discards).toHaveLength(mockTableState.oppDiscards.length)
    expect(seats.find((seat) => seat.seat === 'Left')?.flowers).toHaveLength(mockTableState.leftFlowers.length)
    expect(seats.find((seat) => seat.seat === 'Right')?.melds).toHaveLength(mockTableState.rightMelds.length)
  })

  it('renders fixed discard grids and high-count seat content', () => {
    render(<TableV2 table={mockTableState} />)

    expect(screen.getByLabelText('mahjong-table-v2')).toBeInTheDocument()
    expect(within(screen.getByLabelText('user-discard-grid-v2')).getAllByLabelText(/^tile-/)).toHaveLength(
      mockTableState.selfDiscards.length,
    )
    expect(within(screen.getByLabelText('opponent-discard-grid-v2')).getAllByLabelText(/^tile-/)).toHaveLength(
      mockTableState.oppDiscards.length,
    )
    expect(within(screen.getByLabelText('left-flowers-v2')).getAllByLabelText(/^tile-/)).toHaveLength(
      mockTableState.leftFlowers.length,
    )
    expect(within(screen.getByLabelText('right-melds-v2')).getAllByLabelText(/^tile-/)).toHaveLength(
      mockTableState.rightMelds.flat().length,
    )
    expect(screen.getByLabelText('player-panel-user-v2')).toBeInTheDocument()
    expect(screen.getByLabelText('player-panel-opponent-v2')).toBeInTheDocument()
  })

  it('renders the V2 stress anchor with capped fixed discard slots per seat', () => {
    const table = resolveTableStateFromSearch('?anchor=anchor-v2-stress')
    render(<TableV2 table={table} />)

    expect(within(screen.getByLabelText('user-discard-grid-v2')).getAllByLabelText(/^tile-/)).toHaveLength(24)
    expect(within(screen.getByLabelText('opponent-discard-grid-v2')).getAllByLabelText(/^tile-/)).toHaveLength(24)
    expect(within(screen.getByLabelText('left-discard-grid-v2')).getAllByLabelText(/^tile-/)).toHaveLength(24)
    expect(within(screen.getByLabelText('right-discard-grid-v2')).getAllByLabelText(/^tile-/)).toHaveLength(24)
  })

  it('renders opponent concealed hands plus drawn slots in fixed compact regions', () => {
    const table = resolveTableStateFromSearch('?anchor=anchor-v2-stress')
    render(<TableV2 table={table} />)

    expect(within(screen.getByLabelText('opponent-hand-v2')).getAllByLabelText(/concealed-/)).toHaveLength(17)
    expect(within(screen.getByLabelText('left-hand-v2')).getAllByLabelText(/concealed-/)).toHaveLength(17)
    expect(within(screen.getByLabelText('right-hand-v2')).getAllByLabelText(/concealed-/)).toHaveLength(17)
  })

  it('exposes layout diagnostics in the text render snapshot', () => {
    const table = resolveTableStateFromSearch('?anchor=anchor-v2-stress')
    render(<TableV2 table={table} />)

    const snapshot = JSON.parse(window.render_game_to_text?.() ?? '{}')
    expect(snapshot.layout.violations).toEqual([])
    expect(snapshot.layout.boxCount).toBeGreaterThan(120)
  })

  it('renders table-state labels and visible action controls for playable context', () => {
    const table = resolveTableStateFromSearch('?anchor=anchor-v2-stress')
    render(<TableV2 table={table} />)

    expect(screen.getByText('目前輪到：自己')).toBeInTheDocument()
    expect(screen.getByText('自己牌河')).toBeInTheDocument()
    expect(screen.getByText('對家牌河')).toBeInTheDocument()
    expect(screen.getByText('上家牌河')).toBeInTheDocument()
    expect(screen.getByText('下家牌河')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '吃' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '碰' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '槓' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '胡' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '過' })).toBeInTheDocument()
    expect(screen.queryByText('輪到你，請選擇操作')).not.toBeInTheDocument()
  })

  it('keeps player panels limited to avatar and score', () => {
    const table = resolveTableStateFromSearch('?anchor=anchor-v2-stress')
    render(<TableV2 table={table} />)

    expect(screen.queryByText('Leaf')).not.toBeInTheDocument()
    expect(screen.queryByText('Space')).not.toBeInTheDocument()
    expect(screen.queryByText('Moka')).not.toBeInTheDocument()
    expect(screen.queryByText('You')).not.toBeInTheDocument()
    expect(screen.queryByText('對家')).not.toBeInTheDocument()
    expect(screen.queryByText('上家')).not.toBeInTheDocument()
    expect(screen.queryByText('下家')).not.toBeInTheDocument()
    expect(screen.queryByText('自己')).not.toBeInTheDocument()
    expect(screen.getByText('37600')).toBeInTheDocument()
  })

  it('keeps self hand click wiring compatible with session actions', () => {
    const onSelectTile = vi.fn()
    const table = {
      ...mockTableState,
      selfHandTileIds: mockTableState.selfHand.map((_, index) => index),
    }
    render(<TableV2 table={table} onSelectTile={onSelectTile} />)

    fireEvent.click(screen.getByRole('button', { name: 'tile-一-horizontal-0' }))
    expect(onSelectTile).toHaveBeenCalledWith(0, 'hand')
  })
})
