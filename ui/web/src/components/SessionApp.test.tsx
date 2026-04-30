import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { SessionApp } from './SessionApp'
import type { SessionSnapshot } from '../state/tableStore'

function makeSnapshot(overrides: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return {
    sessionId: 'session-123',
    status: 'awaiting_action',
    table: {
      anchorId: 'engine-live',
      activeSeat: 'User',
      drawSeat: 'User',
      wind: '東',
      round: 1,
      timer: 60,
      players: [
        { id: 'p0', pid: 0, name: 'You', seat: 'User', score: 1000, seatWind: '東', isDealer: true },
        { id: 'p1', pid: 1, name: 'Moka', seat: 'Right', score: 1000, seatWind: '南' },
        { id: 'p2', pid: 2, name: 'Leaf', seat: 'Opponent', score: 1000, seatWind: '西' },
        { id: 'p3', pid: 3, name: 'Space', seat: 'Left', score: 1000, seatWind: '北' },
      ],
      selfHand: ['一萬', '二萬', '三萬'],
      selfHandTileIds: [0, 1, 2],
      selfDrawn: '四萬',
      selfDrawnTileId: 3,
      selfDiscards: [],
      selfFlowers: [],
      selfMelds: [],
      oppHand: Array.from({ length: 10 }, () => '牌'),
      oppDiscards: [],
      oppFlowers: [],
      oppMelds: [],
      leftHand: Array.from({ length: 10 }, () => '牌'),
      leftDiscards: [],
      leftFlowers: [],
      leftMelds: [],
      rightHand: Array.from({ length: 10 }, () => '牌'),
      rightDiscards: [],
      rightFlowers: [],
      rightMelds: [],
    },
    legalActions: [{ type: 'DISCARD', tile: 0, from: 'hand' }],
    result: null,
    meta: {
      handIndex: 1,
      jangIndex: 1,
      dealerPid: 0,
      dealerSeat: 'User',
      quanFeng: '東',
      phase: 'TURN',
      activeSeat: 'User',
      drawSeat: 'User',
      humanPid: 0,
    },
    ...overrides,
  }
}

describe('SessionApp', () => {
  afterEach(() => {
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('creates a new session and submits the selected discard action', async () => {
    const initialSnapshot = makeSnapshot()
    const afterAction = makeSnapshot({
      legalActions: [],
      status: 'hand_result',
      result: {
        payments: [20, -20, 0, 0],
        totalsAfterHand: [1020, 980, 1000, 1000],
        winnerPid: 0,
        winnerSeat: 'User',
        winSource: 'TSUMO',
        winnerBreakdown: [{ label: '自摸', points: 1 }],
      },
    })

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(initialSnapshot), { status: 201, headers: { 'Content-Type': 'application/json' } }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(afterAction), { status: 200, headers: { 'Content-Type': 'application/json' } }),
      )
    vi.stubGlobal('fetch', fetchMock)

    render(<SessionApp />)

    await screen.findByRole('button', { name: 'New Game' })

    fireEvent.click(screen.getByRole('button', { name: 'tile-一萬-horizontal-0' }))
    fireEvent.click(screen.getByRole('button', { name: '打出 一萬' }))

    await screen.findByRole('button', { name: 'Continue' })
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/session/session-123/action',
      expect.objectContaining({
        method: 'POST',
      }),
    )
    expect(window.localStorage.getItem('mahjong16.session_id')).toBe('session-123')
  })

  it('falls back to creating a new session when the stored session is gone', async () => {
    window.localStorage.setItem('mahjong16.session_id', 'stale-session')
    const freshSnapshot = makeSnapshot({ sessionId: 'fresh-session' })

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: 'unknown session id: stale-session' }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(freshSnapshot), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    render(<SessionApp />)

    await screen.findByRole('button', { name: 'New Game' })
    await waitFor(() => {
      expect(window.localStorage.getItem('mahjong16.session_id')).toBe('fresh-session')
    })
  })

  it('keeps tsumo-capable turn states on the turn action layout', async () => {
    const snapshot = makeSnapshot({
      legalActions: [
        { type: 'HU', source: 'TSUMO' },
        { type: 'DISCARD', tile: 0, from: 'hand' },
      ],
      meta: {
        ...makeSnapshot().meta,
        phase: 'TURN',
      },
    })

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(
        new Response(JSON.stringify(snapshot), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    render(<SessionApp />)

    await screen.findByRole('button', { name: 'New Game' })
    expect(screen.getByText('先點自己的手牌或摸進牌')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '胡牌' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '打出 一萬' })).not.toBeInTheDocument()
  })
})
