import { colors } from '../styles/tokens'

type CenterConsoleProps = {
  wind: 'East' | 'South' | 'West' | 'North'
  round: number
  timer: number
}

export function CenterConsole({ wind, round, timer }: CenterConsoleProps) {
  return (
    <div className="center-console-panel" aria-label="center-console">
      <div className="label">Current Wind</div>
      <div className="value" style={{ color: colors.accent }}>
        {wind} {round}
      </div>
      <div className="label">Timer</div>
      <div className="value">{timer.toString().padStart(2, '0')}</div>
    </div>
  )
}
