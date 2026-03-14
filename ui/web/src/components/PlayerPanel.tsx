import { colors } from '../styles/tokens'
import type { Seat } from '../state/tableStore'

type PlayerPanelProps = {
  name: string
  seat: Seat
  score: number
  seatLabel?: string
}

export function PlayerPanel({ name, seat, score, seatLabel }: PlayerPanelProps) {
  const initials = name.slice(0, 1).toUpperCase()
  const displaySeat = seatLabel ?? seat
  return (
    <div className={`panel player-panel player-panel-${seat.toLowerCase()}`}>
      <div className="player-meta">
        <div className="avatar" aria-label={`${name} avatar`}>
          {initials}
        </div>
        <div>
          <div style={{ fontWeight: 700 }}>{name}</div>
          <div className="seat-chip" style={{ color: colors.textPrimary }}>
            {displaySeat}
          </div>
        </div>
      </div>
      <div className="score">{score.toLocaleString()}</div>
    </div>
  )
}
