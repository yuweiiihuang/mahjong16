import { useEffect, useMemo } from 'react'
import { CenterConsole } from './CenterConsole'
import { HandRail } from './HandRail'
import { PlayerPanel } from './PlayerPanel'
import { resolveTableStateFromSearch } from '../state/tableStore'
import type { PlayerState, Seat } from '../state/tableStore'

declare global {
  interface Window {
    render_game_to_text?: () => string
  }
}

export function Table() {
  const table = useMemo(() => resolveTableStateFromSearch(window.location.search), [])
  const seatLabels: Record<Seat, string> = {
    User: '自己',
    Opponent: '對家',
    Left: '上家',
    Right: '下家',
  }
  const getPlayer = (seat: Seat): PlayerState => {
    return (
      table.players.find((player) => player.seat === seat) ?? {
        id: `fallback-${seat}`,
        name: seatLabels[seat],
        seat,
        score: 0,
      }
    )
  }
  const opponentPlayer = getPlayer('Opponent')
  const leftPlayer = getPlayer('Left')
  const rightPlayer = getPlayer('Right')
  const userPlayer = getPlayer('User')
  const oppDiscardColumns = 7
  const selfDiscardColumns = 7
  const selfDiscardRows = Math.max(1, Math.ceil(table.selfDiscards.length / selfDiscardColumns))
  const sideDiscardRows = 7
  const rightDiscardColumns = Math.max(1, Math.ceil(table.rightDiscards.length / sideDiscardRows))
  const sideTotalUnits = 16
  const oppTotalUnits = 16
  const selfTotalUnits = 16
  const meldUnits = Math.min(selfTotalUnits - 1, table.selfMelds.length * 3)
  const handUnits = Math.max(1, selfTotalUnits - meldUnits)
  const totalUnits = meldUnits + handUnits
  const oppHandUnits = oppTotalUnits
  const leftMeldUnits = Math.min(sideTotalUnits - 1, table.leftMelds.length * 3)
  const rightMeldUnits = Math.min(sideTotalUnits - 1, table.rightMelds.length * 3)
  const leftHandUnits = Math.max(1, sideTotalUnits - leftMeldUnits)
  const rightHandUnits = Math.max(1, sideTotalUnits - rightMeldUnits)

  useEffect(() => {
    window.render_game_to_text = () =>
      JSON.stringify({
        mode: 'layout-static',
        wind: table.wind,
        round: table.round,
        timer: table.timer,
        players: table.players.map((player) => ({
          seat: player.seat,
          name: player.name,
          score: player.score,
        })),
        activeSeat: table.activeSeat,
        drawSeat: table.drawSeat,
        counts: {
          selfHand: table.selfHand.length,
          selfDiscards: table.selfDiscards.length,
          selfMelds: table.selfMelds.length,
          oppHand: table.oppHand.length,
          oppDiscards: table.oppDiscards.length,
          leftHand: table.leftHand.length,
          leftDiscards: table.leftDiscards.length,
          rightHand: table.rightHand.length,
          rightDiscards: table.rightDiscards.length,
        },
        coordinates: 'origin at viewport top-left; +x to right, +y to bottom',
      })

    return () => {
      delete window.render_game_to_text
    }
  }, [table])

  return (
    <div className="table-shell">
      <div className="table-edge-strip" />
      <div className="player-panels">
        <div className="player-panel-slot seat-opponent" aria-label="player-panel-opponent">
          <PlayerPanel
            name={opponentPlayer.name}
            seat={opponentPlayer.seat}
            score={opponentPlayer.score}
            seatLabel={seatLabels[opponentPlayer.seat]}
          />
        </div>
        <div className="player-panel-slot seat-left" aria-label="player-panel-left">
          <PlayerPanel
            name={leftPlayer.name}
            seat={leftPlayer.seat}
            score={leftPlayer.score}
            seatLabel={seatLabels[leftPlayer.seat]}
          />
        </div>
        <div className="player-panel-slot seat-right" aria-label="player-panel-right">
          <PlayerPanel
            name={rightPlayer.name}
            seat={rightPlayer.seat}
            score={rightPlayer.score}
            seatLabel={seatLabels[rightPlayer.seat]}
          />
        </div>
        <div className="player-panel-slot seat-user" aria-label="player-panel-user">
          <PlayerPanel
            name={userPlayer.name}
            seat={userPlayer.seat}
            score={userPlayer.score}
            seatLabel={seatLabels[userPlayer.seat]}
          />
        </div>
      </div>

      <div className="table-grid">
        {/* 對家 */}
        <div className="region color-opponent opp-hand">
          <div className="region-content">
            <div
              className="top-rail"
              style={{
                ['--top-units' as keyof React.CSSProperties]: oppTotalUnits.toString(),
                ['--hand-units' as keyof React.CSSProperties]: oppHandUnits.toString(),
              }}
            >
              <div className="top-hand">
                <div className="region-title">對家 手牌 / 副露</div>
                <HandRail labels={table.oppHand.slice(0, oppHandUnits)} />
              </div>
            </div>
          </div>
        </div>
        <div className="region color-opponent opp-draw">
          <span className="region-label">進牌</span>
          {table.drawSeat === 'Opponent' ? <div className="tile draw-tile" data-label="進" /> : null}
        </div>
        <div className="region color-opponent opp-discard">
          <div className="region-content">
            <div className="region-title">對家 棄牌</div>
            <div className="discard-grid-opp" aria-label="opp-discard-grid">
              {table.oppDiscards.map((_, idx) => (
                <div
                  key={`opp-discard-${idx}`}
                  className="tile"
                  data-label={`${idx + 1}`}
                  style={
                    {
                      gridColumn: oppDiscardColumns - (idx % oppDiscardColumns),
                      gridRow: Math.floor(idx / oppDiscardColumns) + 1,
                    } as React.CSSProperties
                  }
                />
              ))}
            </div>
          </div>
        </div>
        <div className="region color-opponent opp-flower">
          <span className="region-label">對家 花牌</span>
        </div>

        {/* 我方 */}
        <div className="region color-user self-hand">
          <div className="region-content">
            <div
              className="bottom-rail"
              style={{
                ['--bottom-units' as keyof React.CSSProperties]: totalUnits.toString(),
                ['--meld-units' as keyof React.CSSProperties]: meldUnits.toString(),
                ['--hand-units' as keyof React.CSSProperties]: handUnits.toString(),
              }}
            >
              <div className="bottom-melds">
                <div className="region-title">我的 副露</div>
                <div className="melds">
                  {table.selfMelds.map((meld, idx) => (
                    <HandRail key={`self-meld-${idx}`} labels={meld} />
                  ))}
                </div>
              </div>
              <div className="bottom-hand">
                <div className="region-title">自己的 手牌</div>
                <HandRail labels={table.selfHand} />
              </div>
            </div>
          </div>
        </div>
        <div className="region color-user self-draw">
          <span className="region-label">進牌</span>
          {table.drawSeat === 'User' ? <div className="tile draw-tile" data-label="進" /> : null}
        </div>
        <div className="region color-user self-discard">
          <div className="region-content">
            <div className="region-title">我的 棄牌</div>
            <div className="discard-grid-self" aria-label="self-discard-grid">
              {table.selfDiscards.map((_, idx) => (
                <div
                  key={`self-discard-${idx}`}
                  className="tile"
                  data-label={`${idx + 1}`}
                  style={
                    {
                      gridColumn: (idx % selfDiscardColumns) + 1,
                      gridRow: selfDiscardRows - Math.floor(idx / selfDiscardColumns),
                    } as React.CSSProperties
                  }
                />
              ))}
            </div>
          </div>
        </div>
        <div className="region color-user self-flower">
          <span className="region-label">我的 花牌</span>
        </div>

        {/* 上家 */}
        <div className="region color-left left-meld">
          <span className="region-label">上家 副露</span>
        </div>
        <div className="region color-left left-hand">
          <div className="region-content">
            <div
              className="side-rail"
              style={{
                ['--side-units' as keyof React.CSSProperties]: sideTotalUnits.toString(),
                ['--meld-units' as keyof React.CSSProperties]: leftMeldUnits.toString(),
                ['--hand-units' as keyof React.CSSProperties]: leftHandUnits.toString(),
              }}
            >
              <div className="side-melds">
                <div className="region-title">上家 副露</div>
                <div className="melds vertical">
                  {table.leftMelds.map((meld, idx) => (
                    <HandRail key={`left-meld-${idx}`} labels={meld} orientation="vertical" />
                  ))}
                </div>
              </div>
              <div className="side-hand">
                <div className="region-title">上家 手牌</div>
                <HandRail
                  labels={table.leftHand.slice(0, leftHandUnits)}
                  orientation="vertical"
                />
              </div>
            </div>
          </div>
        </div>
        <div className="region color-left left-draw">
          <span className="region-label">進牌</span>
          {table.drawSeat === 'Left' ? (
            <div className="tile draw-tile draw-left" data-label="進" />
          ) : null}
        </div>
        <div className="region color-left left-discard">
          <div className="region-content">
            <div className="region-title">上家 棄牌</div>
            <div className="discard-grid-vertical" aria-label="left-discard-grid">
              {table.leftDiscards.map((_, idx) => (
                <div key={`left-discard-${idx}`} className="tile" data-label={`${idx + 1}`} />
              ))}
            </div>
          </div>
        </div>
        <div className="region color-left left-flower">
          <span className="region-label">上家 花牌</span>
        </div>

        {/* 下家 */}
        <div className="region color-right right-meld">
          <span className="region-label">下家 副露</span>
        </div>
        <div className="region color-right right-hand">
          <div className="region-content">
            <div
              className="side-rail"
              style={{
                ['--side-units' as keyof React.CSSProperties]: sideTotalUnits.toString(),
                ['--meld-units' as keyof React.CSSProperties]: rightMeldUnits.toString(),
                ['--hand-units' as keyof React.CSSProperties]: rightHandUnits.toString(),
              }}
            >
              <div className="side-melds">
                <div className="region-title">下家 副露</div>
                <div className="melds vertical">
                  {table.rightMelds.map((meld, idx) => (
                    <HandRail key={`right-meld-${idx}`} labels={meld} orientation="vertical" />
                  ))}
                </div>
              </div>
              <div className="side-hand">
                <div className="region-title">下家 手牌</div>
                <HandRail
                  labels={table.rightHand.slice(0, rightHandUnits)}
                  orientation="vertical"
                />
              </div>
            </div>
          </div>
        </div>
        <div className="region color-right right-draw">
          <span className="region-label">進牌</span>
          {table.drawSeat === 'Right' ? (
            <div className="tile draw-tile draw-right" data-label="進" />
          ) : null}
        </div>
        <div className="region color-right right-discard">
          <div className="region-content">
            <div className="region-title">下家 棄牌</div>
            <div className="discard-grid-vertical" aria-label="right-discard-grid">
              {table.rightDiscards.map((_, idx) => (
                <div
                  key={`right-discard-${idx}`}
                  className="tile"
                  data-label={`${idx + 1}`}
                  style={
                    {
                      gridColumn: rightDiscardColumns - Math.floor(idx / sideDiscardRows),
                      gridRow: sideDiscardRows - (idx % sideDiscardRows),
                    } as React.CSSProperties
                  }
                />
              ))}
            </div>
          </div>
        </div>
        <div className="region color-right right-flower">
          <span className="region-label">下家 花牌</span>
        </div>

        {/* 中央資訊 */}
        <div className="center-console-cell">
          <CenterConsole wind={table.wind} round={table.round} timer={table.timer} />
        </div>
      </div>
    </div>
  )
}
