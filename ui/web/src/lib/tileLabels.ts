import type { SessionAction } from '../state/tableStore'

const digits: Record<number, string> = {
  1: '一',
  2: '二',
  3: '三',
  4: '四',
  5: '五',
  6: '六',
  7: '七',
  8: '八',
  9: '九',
}

const honors: Record<number, string> = {
  27: '東',
  28: '南',
  29: '西',
  30: '北',
  31: '中',
  32: '發',
  33: '白',
}

const suits: Record<number, string> = {
  0: '萬',
  1: '筒',
  2: '條',
}

export function tileIdToLabel(tileId: number): string {
  if (tileId >= 34) {
    return `花${tileId - 33}`
  }
  if (tileId in honors) {
    return honors[tileId]
  }
  const suit = tileId <= 8 ? 0 : tileId <= 17 ? 1 : 2
  const rank = suit === 0 ? tileId + 1 : suit === 1 ? tileId - 8 : tileId - 17
  return `${digits[rank] ?? String(rank)}${suits[suit]}`
}

function joinChiUse(use: number[] | undefined, tile: number | undefined): string {
  const parts = [...(use ?? []), ...(typeof tile === 'number' ? [tile] : [])]
  return parts.map(tileIdToLabel).join(' ')
}

export function actionToLabel(action: SessionAction): string {
  const kind = action.type.toUpperCase()
  if (kind === 'DISCARD' && typeof action.tile === 'number') {
    return `打出 ${tileIdToLabel(action.tile)}`
  }
  if (kind === 'TING' && typeof action.tile === 'number') {
    return `聽牌打出 ${tileIdToLabel(action.tile)}`
  }
  if (kind === 'HU') {
    return '胡牌'
  }
  if (kind === 'ANGANG' && typeof action.tile === 'number') {
    return `暗槓 ${tileIdToLabel(action.tile)}`
  }
  if (kind === 'KAKAN' && typeof action.tile === 'number') {
    return `加槓 ${tileIdToLabel(action.tile)}`
  }
  if (kind === 'PASS') {
    return '過'
  }
  if (kind === 'PONG' && typeof action.tile === 'number') {
    return `碰 ${tileIdToLabel(action.tile)}`
  }
  if (kind === 'GANG' && typeof action.tile === 'number') {
    return `槓 ${tileIdToLabel(action.tile)}`
  }
  if (kind === 'CHI') {
    return `吃 ${joinChiUse(action.use, action.tile)}`
  }
  return kind
}
