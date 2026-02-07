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
  })
})
