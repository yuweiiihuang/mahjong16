import { colors } from '../styles/tokens'

type PlayerPanelProps = {
  name: string
  seat: string
  score: number
  seatLabel?: string
}

export function PlayerPanel({ name, seat, score, seatLabel }: PlayerPanelProps) {
  const initials = name.slice(0, 1).toUpperCase()
  return (
    <div className="panel player-panel">
      <div className="player-meta">
        <div className="avatar" aria-label={`${name} avatar`}>
          {initials}
        </div>
        <div>
          <div style={{ fontWeight: 700 }}>{name}</div>
          <div style={{ color: colors.textMuted, fontSize: 12 }}>
            {seatLabel ?? seat}
          </div>
        </div>
      </div>
      <div className="score">{score.toLocaleString()}</div>
      <div className="coins" aria-label={`${name} coins`}>
        <span className="coin-dot" />
        <span>100</span>
      </div>
    </div>
  )
}
