import { useEffect, useMemo, useState } from 'react'
import { continueSession, createSession, getSession, submitSessionAction } from '../api/session'
import { actionToLabel, tileIdToLabel } from '../lib/tileLabels'
import { Table } from './Table'
import type { Seat, SessionAction, SessionSnapshot } from '../state/tableStore'

const SESSION_STORAGE_KEY = 'mahjong16.session_id'

type SelectedTile = {
  tileId: number
  source: 'hand' | 'drawn'
}

function isMissingSessionError(error: unknown): boolean {
  return error instanceof Error && /unknown session id/i.test(error.message)
}

function matchesSelected(action: SessionAction, selectedTile: SelectedTile | null): boolean {
  if (!selectedTile) {
    return false
  }
  const kind = action.type.toUpperCase()
  if (kind !== 'DISCARD' && kind !== 'TING') {
    return false
  }
  return action.tile === selectedTile.tileId && (action.from ?? 'hand') === selectedTile.source
}

function seatName(seat: Seat | null): string {
  if (seat === 'User') return '自己'
  if (seat === 'Left') return '上家'
  if (seat === 'Right') return '下家'
  if (seat === 'Opponent') return '對家'
  return '未知'
}

export function SessionApp() {
  const [snapshot, setSnapshot] = useState<SessionSnapshot | null>(null)
  const [selectedTile, setSelectedTile] = useState<SelectedTile | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function boot() {
      setLoading(true)
      setError(null)
      const storedSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY)

      try {
        let nextSnapshot: SessionSnapshot
        if (storedSessionId) {
          try {
            nextSnapshot = await getSession(storedSessionId)
          } catch (sessionError) {
            if (!isMissingSessionError(sessionError)) {
              throw sessionError
            }
            nextSnapshot = await createSession()
          }
        } else {
          nextSnapshot = await createSession()
        }

        if (cancelled) {
          return
        }

        window.localStorage.setItem(SESSION_STORAGE_KEY, nextSnapshot.sessionId)
        setSnapshot(nextSnapshot)
      } catch (bootError) {
        if (!cancelled) {
          setError(bootError instanceof Error ? bootError.message : '無法初始化牌局')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void boot()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!snapshot || !selectedTile) {
      return
    }
    const stillAvailable = snapshot.legalActions.some((action) => matchesSelected(action, selectedTile))
    if (!stillAvailable) {
      setSelectedTile(null)
    }
  }, [snapshot, selectedTile])

  const phaseActions = useMemo(() => {
    if (!snapshot) {
      return {
        selectedActions: [] as SessionAction[],
        specialTurnActions: [] as SessionAction[],
      }
    }
    const selectedActions = snapshot.legalActions.filter((action) => matchesSelected(action, selectedTile))
    const specialTurnActions = snapshot.legalActions.filter((action) => {
      const kind = action.type.toUpperCase()
      return kind === 'HU' || kind === 'ANGANG' || kind === 'KAKAN'
    })

    return { selectedActions, specialTurnActions }
  }, [selectedTile, snapshot])

  async function withRequest(work: () => Promise<SessionSnapshot>) {
    setBusy(true)
    setError(null)
    try {
      const nextSnapshot = await work()
      window.localStorage.setItem(SESSION_STORAGE_KEY, nextSnapshot.sessionId)
      setSnapshot(nextSnapshot)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '請求失敗')
    } finally {
      setBusy(false)
    }
  }

  function onNewGame() {
    setSelectedTile(null)
    void withRequest(() => createSession())
  }

  function onAction(action: SessionAction) {
    if (!snapshot) {
      return
    }
    setSelectedTile(null)
    void withRequest(() => submitSessionAction(snapshot.sessionId, action))
  }

  function onContinue() {
    if (!snapshot) {
      return
    }
    setSelectedTile(null)
    void withRequest(() => continueSession(snapshot.sessionId))
  }

  if (loading) {
    return <div className="session-empty">正在建立牌局…</div>
  }

  if (error && !snapshot) {
    return (
      <div className="session-empty">
        <div>無法載入 Mahjong16 Web Session</div>
        <div className="session-error-text">{error}</div>
        <button type="button" className="control-button primary" onClick={onNewGame}>
          Retry
        </button>
      </div>
    )
  }

  if (!snapshot) {
    return <div className="session-empty">尚未載入牌局。</div>
  }

  const isReaction = snapshot.meta.phase === 'REACTION'
  const selectedTileLabel = selectedTile ? tileIdToLabel(selectedTile.tileId) : null

  return (
    <div className="session-layout">
      <div className="session-header">
        <div className="status-card">
          <div className="status-label">圈風 / 局數</div>
          <div className="status-value">
            {snapshot.meta.quanFeng}圈 · 第 {snapshot.meta.handIndex} 手
          </div>
        </div>
        <div className="status-card">
          <div className="status-label">當前狀態</div>
          <div className="status-value">
            {snapshot.status === 'awaiting_action'
              ? `等待 ${seatName(snapshot.meta.activeSeat)} 操作`
              : snapshot.status === 'hand_result'
                ? '本手結算'
                : '牌局結束'}
          </div>
        </div>
      </div>

      <div className="table-outer live-session">
        <Table
          table={snapshot.table}
          selectedTile={selectedTile}
          onSelectTile={(tileId, source) => setSelectedTile({ tileId, source })}
        />
      </div>

      <aside className="control-dock">
        <div className="control-card">
          <div className="control-title">Session</div>
          <div className="control-meta">
            <span>Session: {snapshot.sessionId.slice(0, 8)}</span>
            <span>莊家: {seatName(snapshot.meta.dealerSeat)}</span>
            <span>剩餘牌: {snapshot.table.timer}</span>
          </div>
          <div className="control-row">
            <button type="button" className="control-button" onClick={onNewGame} disabled={busy}>
              New Game
            </button>
          </div>
          {error ? <div className="session-error-text">{error}</div> : null}
        </div>

        {snapshot.status === 'awaiting_action' ? (
          <div className="control-card">
            <div className="control-title">操作面板</div>
            {selectedTileLabel ? (
              <div className="selected-tile">已選牌：{selectedTileLabel}</div>
            ) : (
              <div className="selected-tile muted">先點自己的手牌或摸進牌</div>
            )}

            {phaseActions.selectedActions.length > 0 ? (
              <div className="action-grid">
                {phaseActions.selectedActions.map((action, index) => (
                  <button
                    key={`${action.type}-${action.tile}-${action.from}-${index}`}
                    type="button"
                    className="control-button primary"
                    onClick={() => onAction(action)}
                    disabled={busy}
                  >
                    {actionToLabel(action)}
                  </button>
                ))}
              </div>
            ) : null}

            {!isReaction && phaseActions.specialTurnActions.length > 0 ? (
              <div className="action-grid">
                {phaseActions.specialTurnActions.map((action, index) => (
                  <button
                    key={`${action.type}-${action.tile}-${index}`}
                    type="button"
                    className="control-button"
                    onClick={() => onAction(action)}
                    disabled={busy}
                  >
                    {actionToLabel(action)}
                  </button>
                ))}
              </div>
            ) : null}

            {isReaction ? (
              <div className="action-grid">
                {snapshot.legalActions.map((action, index) => (
                  <button
                    key={`${action.type}-${action.tile}-${action.use?.join('-') ?? 'none'}-${index}`}
                    type="button"
                    className={`control-button ${action.type.toUpperCase() === 'PASS' ? '' : 'primary'}`}
                    onClick={() => onAction(action)}
                    disabled={busy}
                  >
                    {actionToLabel(action)}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {snapshot.result ? (
          <div className="control-card result-card">
            <div className="control-title">本手結算</div>
            <div className="result-line">
              {snapshot.result.winnerSeat
                ? `${seatName(snapshot.result.winnerSeat)} ${snapshot.result.winSource ?? ''}`
                : '流局'}
            </div>
            <div className="payment-grid">
              {snapshot.table.players.map((player) => {
                const delta =
                  snapshot.result?.payments[player.pid ?? 0] ??
                  0
                return (
                  <div key={player.id} className="payment-row">
                    <span>{player.name}</span>
                    <span className={delta >= 0 ? 'delta-positive' : 'delta-negative'}>
                      {delta >= 0 ? '+' : ''}
                      {delta}
                    </span>
                  </div>
                )
              })}
            </div>
            {snapshot.result.winnerBreakdown.length > 0 ? (
              <div className="breakdown-list">
                {snapshot.result.winnerBreakdown.map((item, index) => (
                  <div key={`${item.key ?? item.label ?? 'breakdown'}-${index}`} className="breakdown-row">
                    <span>{item.label ?? item.key ?? '未命名'}</span>
                    <span>{item.points ?? 0}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="selected-tile muted">本手沒有計分項目。</div>
            )}

            {snapshot.status === 'hand_result' ? (
              <button
                type="button"
                className="control-button primary"
                onClick={onContinue}
                disabled={busy}
              >
                Continue
              </button>
            ) : null}
          </div>
        ) : null}
      </aside>
    </div>
  )
}
