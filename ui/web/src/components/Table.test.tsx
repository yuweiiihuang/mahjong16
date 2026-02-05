import { render, screen } from '@testing-library/react'
import { Table } from './Table'

describe('Table', () => {
  it('renders center console and player panels', () => {
    const { container } = render(<Table />)

    expect(screen.getByLabelText('center-console')).toBeInTheDocument()
    expect(screen.getByText(/Current Wind/i)).toBeInTheDocument()
    // region placeholders should fill the grid
    const regions = container.querySelectorAll('.region')
    expect(regions.length).toBe(16) // 4 seats *4 zones (center console not counted as region)

    // tiles rendered for all hands, melds, and discards
    expect(container.querySelectorAll('.tile').length).toBe(70)
  })
})
