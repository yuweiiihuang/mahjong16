type Seat = 'User' | 'Opponent' | 'Right' | 'Left'

const seatWindTiles = [
  {
    seat: 'User' as const,
    positionClass: 'bottom-right',
    rotationClass: 'rotate-0',
  },
  {
    seat: 'Right' as const,
    positionClass: 'top-right',
    rotationClass: 'rotate-left-90',
  },
  {
    seat: 'Opponent' as const,
    positionClass: 'top-left',
    rotationClass: 'rotate-180',
  },
  {
    seat: 'Left' as const,
    positionClass: 'bottom-left',
    rotationClass: 'rotate-right-90',
  },
] as const

type CenterConsoleProps = {
  drawSeat: Seat | null
  activeSeat?: Seat | null
  seatWinds: Record<Seat, string>
}

export function CenterConsole({ drawSeat, activeSeat, seatWinds }: CenterConsoleProps) {
  return (
    <div className="center-console-panel" aria-label="center-console">
      {seatWindTiles.map((tile) => (
        <div
          key={tile.seat}
          className={[
            'seat-wind-tile',
            tile.positionClass,
            drawSeat === tile.seat ? 'is-drawing' : '',
            activeSeat === tile.seat ? 'is-active' : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <span className={`wind ${tile.rotationClass}`}>{seatWinds[tile.seat]}</span>
        </div>
      ))}
    </div>
  )
}
