import { useMemo } from 'react'
import { CenterConsole } from './CenterConsole'
import { HandRail } from './HandRail'
import { mockTableState } from '../state/tableStore'

export function Table() {
  const table = useMemo(() => mockTableState, [])
  const meldUnits = Math.max(1, table.selfMelds.length * 3)
  const handUnits = Math.max(1, table.selfHand.length)
  const totalUnits = meldUnits + handUnits

  return (
    <div className="table-shell">
      <div className="table-edge-strip" />

      <div className="table-grid">
        {/* 對家 */}
        <div className="region color-opponent opp-meld">對家 副露</div>
        <div className="region color-opponent opp-hand">
          <div className="region-content">
            <div className="region-title">對家 手牌</div>
            <HandRail labels={table.oppHand} />
          </div>
        </div>
        <div className="region color-opponent opp-discard">對家 棄牌</div>
        <div className="region color-opponent opp-flower">對家 花牌</div>

        {/* 我方 */}
        <div
          className="self-row"
          style={{
            ['--meld-units' as keyof React.CSSProperties]: meldUnits.toString(),
            ['--hand-units' as keyof React.CSSProperties]: handUnits.toString(),
            ['--self-units' as keyof React.CSSProperties]: totalUnits.toString(),
          }}
        >
          <div className="region color-user self-meld">
            <div className="region-content">
              <div className="region-title">我的 副露</div>
              <div className="melds">
                {table.selfMelds.map((meld, idx) => (
                  <HandRail key={`meld-${idx}`} labels={meld} />
                ))}
              </div>
            </div>
          </div>
          <div className="region color-user self-hand">
            <div className="region-content">
              <div className="region-title">自己的 手牌</div>
              <HandRail labels={table.selfHand} />
            </div>
          </div>
        </div>
        <div className="region color-user self-discard">
          <div className="region-content">
            <div className="region-title">我的 棄牌</div>
            <HandRail labels={table.selfDiscards} />
          </div>
        </div>
        <div className="region color-user self-flower">我的 花牌</div>

        {/* 上家 */}
        <div className="region color-left left-meld">上家 副露</div>
        <div className="region color-left left-hand">
          <div className="region-content">
            <div className="region-title">上家 手牌</div>
            <HandRail labels={table.leftHand} orientation="vertical" />
          </div>
        </div>
        <div className="region color-left left-discard">上家 棄牌</div>
        <div className="region color-left left-flower">上家 花牌</div>

        {/* 下家 */}
        <div className="region color-right right-meld">下家 副露</div>
        <div className="region color-right right-hand">
          <div className="region-content">
            <div className="region-title">下家 手牌</div>
            <HandRail labels={table.rightHand} orientation="vertical" />
          </div>
        </div>
        <div className="region color-right right-discard">下家 棄牌</div>
        <div className="region color-right right-flower">下家 花牌</div>

        {/* 中央資訊 */}
        <div className="center-console-cell">
          <CenterConsole wind={table.wind} round={table.round} timer={table.timer} />
        </div>
      </div>
    </div>
  )
}
