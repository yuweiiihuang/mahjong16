import { useEffect } from 'react'
import type { Seat, TableState } from '../../state/tableStore'
import {
  CENTER_CONSOLE_ZONE,
  FELT,
  PLAYER_CARD_ZONES,
  SCENE_H,
  SCENE_W,
  collectLayoutBoxes,
  findLayoutViolations,
} from './layout'
import { HandDockV2 } from './HandDockV2'
import { MeldFlowerLayerV2 } from './MeldFlowerLayerV2'
import { OpponentHandLayerV2 } from './OpponentHandLayerV2'
import { RiverLayerV2 } from './RiverLayerV2'
import { TABLE_REGIONS } from './layout/regions'
import { tableStateToSeatViews } from './tableAdapter'
import type { SelectedTile, TileSource } from './types'

type TableV2Props = {
  table: TableState
  selectedTile?: SelectedTile | null
  onSelectTile?: (tileId: number, source: TileSource) => void
}

const SEAT_LABELS: Record<Seat, string> = {
  User: '自己',
  Opponent: '對家',
  Left: '上家',
  Right: '下家',
}

const ACTION_LABELS = ['吃', '碰', '槓', '胡', '過']

export function TableV2({ table, selectedTile, onSelectTile }: TableV2Props) {
  const seatViews = tableStateToSeatViews(table)
  const seatWinds = Object.fromEntries(
    seatViews.map((seatView) => [seatView.seat, seatView.player.seatWind ?? ''])
  ) as Record<Seat, string>
  const activeLabel = table.activeSeat ? SEAT_LABELS[table.activeSeat] : '等待'
  const dealer = seatViews.find((seatView) => seatView.player.isDealer)
  const dealerLabel = dealer ? `${SEAT_LABELS[dealer.seat]} ${dealer.player.name}` : '未標示'
  const userSeatView = seatViews.find((seatView) => seatView.seat === 'User')

  useEffect(() => {
    const layoutBoxes = collectLayoutBoxes(seatViews)
    const layoutViolations = findLayoutViolations(layoutBoxes)
    window.render_game_to_text = () =>
      JSON.stringify({
        mode: 'layout-v2',
        scene: { width: SCENE_W, height: SCENE_H },
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
        counts: Object.fromEntries(
          seatViews.map((seatView) => [
            seatView.seat,
            {
              hand: seatView.hand.length,
              melds: seatView.melds.length,
              flowers: seatView.flowers.length,
              discards: seatView.discards.length,
            },
          ]),
        ),
        layout: {
          boxCount: layoutBoxes.length,
          violations: layoutViolations,
        },
      })

    return () => {
      delete window.render_game_to_text
    }
  }, [seatViews, table])

  return (
    <div className="table-v2-scene" aria-label="mahjong-table-v2">
      <div
        className="table-v2-felt"
        style={{
          left: FELT.x,
          top: FELT.y,
          width: FELT.width,
          height: FELT.height,
        }}
      />
      <div className="table-v2-rail table-v2-rail-top" />
      <div className="table-v2-rail table-v2-rail-left" />
      <div className="table-v2-rail table-v2-rail-right" />
      <div className="table-v2-rail table-v2-rail-bottom" />

      <RiverLayerV2 seatViews={seatViews} />
      <MeldFlowerLayerV2 seatViews={seatViews} />
      <OpponentHandLayerV2 seatViews={seatViews} />
      {userSeatView ? (
        <HandDockV2 seatView={userSeatView} selectedTile={selectedTile} onSelectTile={onSelectTile} />
      ) : null}

      <div
        className="center-console-v2"
        style={{
          left: CENTER_CONSOLE_ZONE.x,
          top: CENTER_CONSOLE_ZONE.y,
          width: CENTER_CONSOLE_ZONE.width,
          height: CENTER_CONSOLE_ZONE.height,
        }}
      >
        <div className="center-console-panel center-console-panel-v2" aria-label="center-console">
          <div className="center-console-title-v2">{table.wind} {table.round} 局</div>
          <div className="center-console-line-v2">莊家：{dealerLabel}</div>
          <div className="center-console-line-v2">目前輪到：{activeLabel}</div>
          <div className="center-console-line-v2">剩餘牌數：{table.timer ? 52 : 52}</div>
          <div className="center-console-winds-v2">
            {seatViews.map((seatView) => (
              <span
                key={`${seatView.seat}-wind-chip-v2`}
                className={seatView.seat === table.activeSeat ? 'is-active' : ''}
              >
                {seatWinds[seatView.seat] || '-'}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div
        className="action-strip-v2"
        aria-label="table-actions-v2"
        style={{
          left: TABLE_REGIONS.actionDock.x,
          top: TABLE_REGIONS.actionDock.y,
          width: TABLE_REGIONS.actionDock.width,
          height: TABLE_REGIONS.actionDock.height,
        }}
      >
        <div className="action-strip-buttons-v2">
          {ACTION_LABELS.map((label) => (
            <button key={label} type="button" className="action-button-v2" aria-label={label}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {seatViews.map((seatView) => {
        const position = PLAYER_CARD_ZONES[seatView.seat]
        return (
          <div
            key={`${seatView.seat}-panel-v2`}
            className={`player-panel-v2 player-panel-v2-${seatView.seat.toLowerCase()}${
              seatView.active ? ' is-active' : ''
            }`}
            style={{ left: position.x, top: position.y }}
            aria-label={`player-panel-${seatView.seat.toLowerCase()}-v2`}
          >
            <div className="player-panel-v2-avatar" aria-hidden="true" />
            <div className="player-panel-v2-score">{seatView.player.score.toString()}</div>
          </div>
        )
      })}
    </div>
  )
}
