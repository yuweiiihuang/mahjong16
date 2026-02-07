import { render, screen, within } from '@testing-library/react'
import { Table } from './Table'
import { mockTableState } from '../state/tableStore'

describe('Table', () => {
  it('renders key table regions and discard counts from the mocked state', () => {
    render(<Table />)

    expect(screen.getByLabelText('center-console')).toBeInTheDocument()
    expect(screen.getByText(/Current Wind/i)).toBeInTheDocument()

    const selfDiscardGrid = screen.getByLabelText('self-discard-grid')
    const oppDiscardGrid = screen.getByLabelText('opp-discard-grid')
    const leftDiscardGrid = screen.getByLabelText('left-discard-grid')
    const rightDiscardGrid = screen.getByLabelText('right-discard-grid')
    const playerPanelUser = screen.getByLabelText('player-panel-user')
    const playerPanelOpponent = screen.getByLabelText('player-panel-opponent')
    const playerPanelLeft = screen.getByLabelText('player-panel-left')
    const playerPanelRight = screen.getByLabelText('player-panel-right')

    expect(within(selfDiscardGrid).getAllByRole('generic').length).toBe(
      mockTableState.selfDiscards.length,
    )
    expect(within(oppDiscardGrid).getAllByRole('generic').length).toBe(
      mockTableState.oppDiscards.length,
    )
    expect(within(leftDiscardGrid).getAllByRole('generic').length).toBe(
      mockTableState.leftDiscards.length,
    )
    expect(within(rightDiscardGrid).getAllByRole('generic').length).toBe(
      mockTableState.rightDiscards.length,
    )

    expect(within(playerPanelUser).getByText('You')).toBeInTheDocument()
    expect(within(playerPanelOpponent).getByText('Leaf')).toBeInTheDocument()
    expect(within(playerPanelLeft).getByText('Space')).toBeInTheDocument()
    expect(within(playerPanelRight).getByText('Moka')).toBeInTheDocument()
  })
})
