type Seat = 'User' | 'Opponent' | 'Right' | 'Left'

const seatWindTiles = [
  {
    seat: 'User' as const,
    positionClass: 'bottom-right',
    rotationClass: 'rotate-0',
    wind: '東',
  },
  {
    seat: 'Right' as const,
    positionClass: 'top-right',
    rotationClass: 'rotate-left-90',
    wind: '南',
  },
  {
    seat: 'Opponent' as const,
    positionClass: 'top-left',
    rotationClass: 'rotate-180',
    wind: '西',
  },
  {
    seat: 'Left' as const,
    positionClass: 'bottom-left',
    rotationClass: 'rotate-right-90',
    wind: '北',
  },
] as const

type CenterConsoleProps = {
  drawSeat: Seat | null
}

export function CenterConsole({ drawSeat }: CenterConsoleProps) {
  return (
    <div className="center-console-panel" aria-label="center-console">
      {seatWindTiles.map((tile) => (
        <div
          key={tile.wind}
          className={[
            'seat-wind-tile',
            tile.positionClass,
            drawSeat === tile.seat ? 'is-drawing' : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <span className={`wind ${tile.rotationClass}`}>{tile.wind}</span>
        </div>
      ))}
    </div>
  )
}
