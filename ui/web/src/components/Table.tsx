import { useEffect, useMemo } from 'react'
import { CenterConsole } from './CenterConsole'
import { HandRail } from './HandRail'
import { mockTableState } from '../state/tableStore'

declare global {
  interface Window {
    render_game_to_text?: () => string
  }
}

export function Table() {
  const table = useMemo(() => mockTableState, [])
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
        counts: {
          selfHand: table.selfHand.length,
          selfDiscards: table.selfDiscards.length,
          selfMelds: table.selfMelds.length,
          oppHand: table.oppHand.length,
          leftHand: table.leftHand.length,
          rightHand: table.rightHand.length,
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
          <div className="tile draw-tile" data-label="進" />
        </div>
        <div className="region color-opponent opp-discard">
          <span className="region-label">對家 棄牌</span>
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
          <div className="tile draw-tile" data-label="進" />
        </div>
        <div className="region color-user self-discard">
          <div className="region-content">
            <div className="region-title">我的 棄牌</div>
            <HandRail labels={table.selfDiscards} />
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
          <div className="tile draw-tile draw-left" data-label="進" />
        </div>
        <div className="region color-left left-discard">
          <span className="region-label">上家 棄牌</span>
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
          <div className="tile draw-tile draw-right" data-label="進" />
        </div>
        <div className="region color-right right-discard">
          <span className="region-label">下家 棄牌</span>
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
