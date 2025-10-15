const lastActionEl = document.getElementById('last-action');
const actionMetaEl = document.getElementById('action-meta');
const actionButtonsEl = document.getElementById('action-buttons');
const summaryListEl = document.getElementById('summary-list');
const revealOverlay = document.getElementById('reveal-overlay');
const revealContent = document.getElementById('reveal-content');
const closeRevealBtn = document.getElementById('close-reveal');
const centerSeatEls = {
  north: document.getElementById('center-seat-north'),
  east: document.getElementById('center-seat-east'),
  south: document.getElementById('center-seat-south'),
  west: document.getElementById('center-seat-west'),
};

const slotEls = {
  north: document.getElementById('slot-north'),
  south: document.getElementById('slot-south'),
  east: document.getElementById('slot-east'),
  west: document.getElementById('slot-west'),
};

const defaultSeatToSlot = { E: 'south', S: 'west', W: 'north', N: 'east' };
const windOrder = ['E', 'S', 'W', 'N'];
const slotOrder = ['south', 'west', 'north', 'east'];
const seatGlyph = { E: '東', S: '南', W: '西', N: '北' };
const DEFAULT_RATE = 100;
const statusRateEl = document.getElementById('status-rate');
const statusRoundEl = document.getElementById('status-round');
const statusPhaseEl = document.getElementById('status-phase');
const statusCountdownEl = document.getElementById('status-countdown');
const statusTurnWindEl = document.getElementById('status-turn-wind');
const statusRemainingEl = document.getElementById('status-remaining');
const statusDeadWallEl = document.getElementById('status-dead-wall');
const windTrackEls = {
  south: document.querySelector('[data-wind-slot="south"]'),
  west: document.querySelector('[data-wind-slot="west"]'),
  north: document.querySelector('[data-wind-slot="north"]'),
  east: document.querySelector('[data-wind-slot="east"]'),
};
let currentSerial = null;
let revealDismissed = false;
let latestState = null;
let latestSeatMap = { ...defaultSeatToSlot };
const discardActionLookup = new Map();
let autoPassSerial = null;

const tileSuit = (label) => {
  if (!label) return 'z';
  if (label === '##') return 'concealed';
  const last = label[label.length - 1];
  if ('mps'.includes(last)) return last;
  if ('ESWN'.includes(last)) return 'z';
  if (last === 'z' || last === 'Z') return 'z';
  if ('1234567'.includes(last)) return 'z';
  return 'f';
};

function makeTile(label, { highlight = false } = {}) {
  const span = document.createElement('span');
  span.classList.add('tile');
  const suit = tileSuit(label);
  if (suit === 'concealed') {
    span.classList.add('concealed');
  } else {
    span.classList.add(`suit-${suit}`);
  }
  if (highlight) {
    span.classList.add('highlight');
  }
  span.dataset.label = label ?? '';
  return span;
}

function makeTileBack() {
  const span = document.createElement('span');
  span.classList.add('tile', 'back');
  span.dataset.label = '';
  return span;
}

const formatPoints = (value) => {
  if (value == null) return '—';
  const number = Number(value);
  if (Number.isNaN(number)) {
    return String(value);
  }
  return number.toLocaleString('zh-Hant');
};

const formatSignedPoints = (value) => {
  if (value == null || value === 0) return null;
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  const abs = Math.abs(number).toLocaleString('zh-Hant');
  return `${number > 0 ? '+' : '-'}${abs}`;
};

const kanjiDigits = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'];

function formatHandIndex(value) {
  if (value == null) return '';
  const number = Number(value);
  if (Number.isNaN(number)) {
    return String(value);
  }
  if (number >= 0 && number < kanjiDigits.length) {
    const idx = number <= 0 ? 1 : number;
    return `${kanjiDigits[idx]}局`;
  }
  return `第${number}局`;
}

function seatGlyphLabel(seat) {
  if (!seat) return '—';
  const key = String(seat).toUpperCase();
  return seatGlyph[key] || key;
}

function seatForPid(pid) {
  if (pid == null || !latestState || !Array.isArray(latestState.players)) {
    return null;
  }
  const player = latestState.players.find((entry) => entry && entry.pid === pid);
  if (!player || !player.seat) {
    return null;
  }
  return String(player.seat).toUpperCase();
}

function updateWindLabels() {
  windOrder.forEach((seat) => {
    const slotName = latestSeatMap[seat];
    const el = windTrackEls[slotName];
    if (!el) return;
    el.dataset.wind = seat;
    const letter = el.querySelector('.wind-letter');
    if (letter) {
      letter.textContent = seatGlyph[seat] || seat;
    }
    const ascii = el.querySelector('.wind-ascii');
    if (ascii) {
      ascii.textContent = seat;
    }
  });
}

function updateWindStates(status = {}) {
  Object.values(windTrackEls).forEach((el) => {
    if (!el) return;
    el.classList.remove('is-turn', 'is-dealer');
  });
  const dealerSeat = seatForPid(status.dealer_pid);
  if (dealerSeat) {
    const slotName = latestSeatMap[dealerSeat];
    const el = windTrackEls[slotName];
    if (el) {
      el.classList.add('is-dealer');
    }
  }
  const turnSeat = seatForPid(status.turn);
  if (turnSeat) {
    const slotName = latestSeatMap[turnSeat];
    const el = windTrackEls[slotName];
    if (el) {
      el.classList.add('is-turn');
    }
  }
}

const DEMO_STATE = {
  status: {
    rate: 100,
    quan_feng: 'E',
    hand: 1,
    phase: '出牌',
    turn: 0,
    dealer_pid: 0,
    remaining: 69,
    dead_wall: 14,
    countdown: 38,
    last_action: { who: 'P2', type: '打出', detail: '5p' },
    totals: [8900, 8900, 8900, 9400],
    deltas: [0, 0, 0, 0],
  },
  players: [
    {
      pid: 0,
      seat: 'E',
      name: '玩家一',
      is_dealer: true,
      is_self: true,
      declared_ting: false,
      hand: [
        '1m',
        '1m',
        '1m',
        '3m',
        '3m',
        '4m',
        '4m',
        '5m',
        '6m',
        '7m',
        '7m',
        '3p',
        '4p',
      ],
      drawn: '6p',
      river: ['9m', '9m', 'E', 'E'],
      river_highlight: 3,
      flowers: ['1f'],
      melds: [
        {
          type: 'CHI',
          tiles: ['4s', '5s', '6s'],
          from_pid: 2,
        },
      ],
    },
    {
      pid: 1,
      seat: 'S',
      name: '玩家二',
      is_dealer: false,
      is_self: false,
      declared_ting: true,
      hand_count: 13,
      river: ['2m', '6m', '8p', '1s', '1s', '1s'],
      river_highlight: 5,
      flowers: ['2f', '4f'],
      melds: [
        {
          type: 'PON',
          tiles: ['7p', '7p', '7p'],
          from_pid: 0,
        },
      ],
    },
    {
      pid: 2,
      seat: 'W',
      name: '玩家三',
      is_dealer: false,
      is_self: false,
      declared_ting: false,
      hand_count: 13,
      river: ['3m', '3m', '3m', '9p', '9p'],
      river_highlight: 4,
      flowers: [],
      melds: [
        {
          type: 'CHI',
          tiles: ['2s', '3s', '4s'],
          from_pid: 1,
        },
      ],
    },
    {
      pid: 3,
      seat: 'N',
      name: '玩家四',
      is_dealer: false,
      is_self: false,
      declared_ting: false,
      hand_count: 13,
      river: ['5m', '5m', '5m', 'E', 'E', 'N'],
      river_highlight: 5,
      flowers: ['3f'],
      melds: [
        {
          type: 'PON',
          tiles: ['1z', '1z', '1z'],
          from_pid: 2,
        },
      ],
    },
  ],
  pending_request: {
    serial: 1001,
    player: 0,
    phase: '出牌',
    actions: [
      { id: 'discard-3p', type: 'DISCARD', tile: '3p', source: 'hand' },
      { id: 'discard-4p', type: 'DISCARD', tile: '4p', source: 'hand' },
      { id: 'discard-5p', type: 'DISCARD', tile: '5p', source: 'hand' },
      { id: 'discard-6p', type: 'DISCARD', tile: '6p', source: 'drawn' },
      { id: 'pass', type: 'PASS', label: '跳過' },
    ],
  },
  hand_summaries: [
    {
      hand_index: 1,
      jang_index: 1,
      dealer_pid: 0,
      winner: 3,
      win_source: 'RON',
      win_tile: '3p',
      payments: ['+800', '-800', '0', '0'],
    },
  ],
  reveal: {
    players: [
      {
        pid: 0,
        is_dealer: true,
        hand: ['1m', '1m', '1m', '3m', '3m', '4m', '4m', '5m', '6m', '7m', '7m', '3p', '4p', '6p'],
        melds: [
          {
            type: 'CHI',
            tiles: ['4s', '5s', '6s'],
          },
        ],
        flowers: ['1f'],
        river: ['9m', '9m', 'E', 'E'],
      },
      {
        pid: 1,
        hand: [],
        melds: [
          {
            type: 'PON',
            tiles: ['7p', '7p', '7p'],
          },
        ],
        flowers: ['2f', '4f'],
        river: ['2m', '6m', '8p', '1s', '1s', '1s'],
      },
      {
        pid: 2,
        hand: [],
        melds: [
          {
            type: 'CHI',
            tiles: ['2s', '3s', '4s'],
          },
        ],
        flowers: [],
        river: ['3m', '3m', '3m', '9p', '9p'],
      },
      {
        pid: 3,
        hand: [],
        melds: [
          {
            type: 'PON',
            tiles: ['1z', '1z', '1z'],
          },
        ],
        flowers: ['3f'],
        river: ['5m', '5m', '5m', 'E', 'E', 'N'],
      },
    ],
  },
};

function clearSlots() {
  Object.values(slotEls).forEach((slot) => {
    slot.innerHTML = '';
  });
}

function renderStatus(status = {}) {
  const last = status.last_action;
  if (last) {
    lastActionEl.innerHTML = `<strong>${last.who ?? ''}</strong> ${
      last.type ?? ''
    } ${last.detail ?? ''}`;
  } else {
    lastActionEl.textContent = '等待更新…';
  }
  if (statusRateEl) {
    statusRateEl.textContent = formatPoints(status.rate ?? DEFAULT_RATE);
  }
  if (statusRemainingEl) {
    statusRemainingEl.textContent = formatPoints(status.remaining);
  }
  if (statusDeadWallEl) {
    const dead = status.dead_wall != null ? formatPoints(status.dead_wall) : '—';
    statusDeadWallEl.textContent = `王牌 ${dead}`;
  }
  const handIndex = status.hand ?? status.hand_index ?? null;
  let roundText = '';
  if (status.quan_feng) {
    roundText += seatGlyphLabel(status.quan_feng);
  }
  const handText = formatHandIndex(handIndex);
  if (handText) {
    roundText += handText;
  }
  if (statusRoundEl) {
    statusRoundEl.textContent = roundText || '—';
  }
  if (statusPhaseEl) {
    statusPhaseEl.textContent = status.phase || '等待更新…';
  }
  if (statusCountdownEl) {
    statusCountdownEl.textContent =
      status.countdown != null ? formatPoints(status.countdown) : '--';
  }
  if (statusTurnWindEl) {
    const seat = seatForPid(status.turn);
    statusTurnWindEl.textContent = seat ? `${seatGlyphLabel(seat)}家` : '—';
  }
  updateWindStates(status);
}

function renderPlayer(slot, player, slotName, status) {
  slot.innerHTML = '';
  slot.dataset.pid = player.pid;
  if (player.seat) {
    slot.dataset.seat = player.seat;
  } else {
    delete slot.dataset.seat;
  }
  const displayName =
    player.name || player.nickname || (player.is_self ? '你' : `玩家${player.pid + 1}`);
  slot.dataset.name = displayName;
  slot.classList.toggle('self-player', Boolean(player.is_self));

  const card = document.createElement('div');
  card.className = 'player-card';
  slot.appendChild(card);

  const banner = document.createElement('div');
  banner.className = 'player-banner';
  const avatar = document.createElement('div');
  avatar.className = 'player-avatar';
  const initial = (displayName.trim()[0] || `P${player.pid}`).toUpperCase();
  avatar.textContent = initial;
  if (player.is_self) {
    avatar.classList.add('self');
  }
  if (player.is_dealer) {
    avatar.classList.add('dealer');
  }
  banner.appendChild(avatar);

  const info = document.createElement('div');
  info.className = 'player-info';
  banner.appendChild(info);

  const infoRow = document.createElement('div');
  infoRow.className = 'player-info-row';
  const seatLabel = document.createElement('div');
  seatLabel.className = 'player-seat-label';
  seatLabel.textContent = seatGlyphLabel(player.seat);
  infoRow.appendChild(seatLabel);
  const nameEl = document.createElement('div');
  nameEl.className = 'player-name';
  nameEl.textContent = displayName;
  infoRow.appendChild(nameEl);
  info.appendChild(infoRow);

  const scoreRow = document.createElement('div');
  scoreRow.className = 'player-score-row';
  const coins = document.createElement('div');
  coins.className = 'player-coins';
  const coinIcon = document.createElement('span');
  coinIcon.className = 'coin-icon';
  coins.appendChild(coinIcon);
  const coinValue = document.createElement('span');
  const totals = Array.isArray(status?.totals) ? status.totals : [];
  const totalValue =
    typeof player.pid === 'number' && totals[player.pid] != null
      ? totals[player.pid]
      : null;
  coinValue.textContent = formatPoints(totalValue);
  coins.appendChild(coinValue);
  scoreRow.appendChild(coins);
  const deltas = Array.isArray(status?.deltas) ? status.deltas : [];
  const deltaValue =
    typeof player.pid === 'number' && deltas[player.pid] != null ? deltas[player.pid] : null;
  const deltaText = formatSignedPoints(deltaValue);
  if (deltaText) {
    const deltaEl = document.createElement('div');
    deltaEl.className = 'player-delta';
    if (typeof deltaValue === 'number' && deltaValue < 0) {
      deltaEl.classList.add('negative');
    }
    deltaEl.textContent = deltaText;
    scoreRow.appendChild(deltaEl);
  }
  info.appendChild(scoreRow);

  const tags = document.createElement('div');
  tags.className = 'player-tags';
  const addTag = (label, { highlight = false } = {}) => {
    const tag = document.createElement('span');
    tag.className = 'tag';
    if (highlight) {
      tag.classList.add('highlight');
    }
    tag.textContent = label;
    tags.appendChild(tag);
  };
  if (player.is_self) {
    const handLength = Array.isArray(player.hand) ? player.hand.length : 0;
    addTag('YOU', { highlight: true });
    addTag(`${handLength + (player.drawn ? 1 : 0)} 張`, { highlight: false });
  } else {
    addTag(`${player.hand_count ?? 0} 張`);
  }
  if (player.is_dealer) addTag('莊', { highlight: true });
  if (player.declared_ting) addTag('聽牌', { highlight: true });
  if (tags.childElementCount > 0) {
    info.appendChild(tags);
  }

  card.appendChild(banner);

  const board = document.createElement('div');
  board.className = 'player-board';
  card.appendChild(board);

  const buildZone = (label, builder, { includeEmpty = true } = {}) => {
    const zone = document.createElement('div');
    zone.className = 'player-zone';
    const zoneLabel = document.createElement('div');
    zoneLabel.className = 'player-zone-label';
    zoneLabel.textContent = label;
    zone.appendChild(zoneLabel);
    const content = builder();
    if (content) {
      zone.appendChild(content);
    } else if (includeEmpty) {
      const placeholder = document.createElement('div');
      placeholder.className = 'hidden-count';
      placeholder.textContent = '—';
      zone.appendChild(placeholder);
    }
    return zone;
  };

  if (!player.is_self) {
    const handZone = buildZone('手牌', () => {
      const wrap = document.createElement('div');
      wrap.className = 'tiles-row hand-backs';
      if (slotName) {
        wrap.dataset.seat = slotName;
      }
      const total = Math.max(0, player.hand_count ?? 0);
      for (let idx = 0; idx < total; idx += 1) {
        wrap.appendChild(makeTileBack());
      }
      return wrap;
    });
    board.appendChild(handZone);
  }

  const riverZone = buildZone('河牌', () => {
    if (!player.river || player.river.length === 0) {
      return null;
    }
    const wrap = document.createElement('div');
    wrap.className = 'river-area';
    player.river.forEach((tile, idx) => {
      wrap.appendChild(
        makeTile(tile, { highlight: idx === player.river_highlight })
      );
    });
    return wrap;
  });
  board.appendChild(riverZone);

  const includeFlowers =
    player.is_self || (player.flowers && player.flowers.length > 0);
  if (includeFlowers) {
    const flowersZone = buildZone('花牌', () => {
      if (!player.flowers || player.flowers.length === 0) {
        return null;
      }
      const wrap = document.createElement('div');
      wrap.className = 'flower-area';
      player.flowers.forEach((tile) => wrap.appendChild(makeTile(tile)));
      return wrap;
    });
    board.appendChild(flowersZone);
  }

  if (player.is_self) {
    const strip = document.createElement('div');
    strip.className = 'self-hand-strip';
    const row = document.createElement('div');
    row.className = 'tiles-row self-hand-row';
    player.hand.forEach((tile) => {
      const tileEl = makeTile(tile);
      tileEl.dataset.source = 'hand';
      row.appendChild(tileEl);
    });
    if (player.drawn) {
      const drawnTile = makeTile(player.drawn);
      drawnTile.classList.add('drawn');
      drawnTile.dataset.source = 'drawn';
      row.appendChild(drawnTile);
    }
    strip.appendChild(row);
    slot.appendChild(strip);
  }

  if (player.melds && player.melds.length > 0) {
    const anchor = document.createElement('div');
    anchor.className = 'meld-anchor';
    const grid = document.createElement('div');
    grid.className = 'meld-grid';
    player.melds.forEach((meld) => {
      const group = document.createElement('div');
      group.className = 'meld-group';
      const tiles = meld.tiles || [];
      tiles.slice(0, 3).forEach((tile) => {
        group.appendChild(makeTile(tile));
      });
      if (tiles.length > 3) {
        const overlay = makeTile(tiles[3]);
        overlay.classList.add('stacked');
        group.appendChild(overlay);
      }
      grid.appendChild(group);
    });
    anchor.appendChild(grid);
    card.appendChild(anchor);
  }
}

function renderPlayers(players = []) {
  clearSlots();
  Object.values(centerSeatEls).forEach((el) => {
    if (!el) return;
    el.textContent = '—';
    delete el.dataset.pid;
    delete el.dataset.seat;
  });
  const seatMap = computeSeatMapping(players);
  latestSeatMap = seatMap;
  updateWindLabels();
  const status = latestState?.status;
  const used = new Set();
  const fallback = ['south', 'west', 'north', 'east'];
  players.forEach((player) => {
    const seat = player.seat ? String(player.seat).toUpperCase() : null;
    let slotName = seat && seatMap[seat];
    if (!slotName || used.has(slotName)) {
      slotName = fallback.find((name) => !used.has(name)) || 'south';
    }
    used.add(slotName);
    const slot = slotEls[slotName];
    if (slot) {
      renderPlayer(slot, player, slotName, status);
    }
    const centerSeat = centerSeatEls[slotName];
    if (centerSeat) {
      centerSeat.textContent = seat ? `${seatGlyphLabel(seat)}家` : `P${player.pid}`;
      centerSeat.dataset.pid = player.pid;
      if (seat) {
        centerSeat.dataset.seat = seat;
      } else {
        delete centerSeat.dataset.seat;
      }
    }
  });
}

function renderActions(pending) {
  actionButtonsEl.innerHTML = '';
  discardActionLookup.clear();
  if (!pending) {
    currentSerial = null;
    autoPassSerial = null;
    actionMetaEl.textContent = '等待其他玩家…';
    bindSelfHandInteractions();
    return;
  }
  if (autoPassSerial !== null && autoPassSerial !== pending.serial) {
    autoPassSerial = null;
  }
  currentSerial = pending.serial;
  actionMetaEl.textContent = `玩家 P${pending.player} · ${pending.phase}`;

  const actionable = [];
  let hasDiscards = false;

  pending.actions.forEach((action) => {
    const type = (action.type || '').toUpperCase();
    if (type === 'DISCARD') {
      const source = action.source || 'hand';
      const tile = action.tile;
      if (tile) {
        discardActionLookup.set(`${tile}:${source}`, action.id);
      }
      hasDiscards = true;
      return;
    }
    actionable.push({ ...action, type });
  });

  const nonPassActions = actionable.filter((action) => action.type !== 'PASS');
  if (
    actionable.length > 0 &&
    nonPassActions.length === 0 &&
    autoPassSerial !== currentSerial
  ) {
    const passAction = actionable.find((action) => action.type === 'PASS');
    if (passAction) {
      autoPassSerial = currentSerial;
      handleActionSelection(passAction, null, { auto: true });
      return;
    }
  }

  actionable.forEach((action) => {
    const btn = document.createElement('button');
    if (['PASS', 'HU'].includes(action.type)) {
      btn.classList.add('secondary');
    }
    btn.innerHTML = `<strong>${action.label}</strong>`;
    if (action.waits && action.waits.length > 0) {
      const waits = document.createElement('div');
      waits.className = 'waits';
      const text = action.waits
        .map((tile, idx) => {
          const remaining = action.waits_remaining?.[idx]?.remaining;
          return `${tile}${remaining !== undefined ? `(${remaining})` : ''}`;
        })
        .join(' · ');
      waits.textContent = `聽牌: ${text}`;
      btn.appendChild(waits);
    }
    btn.addEventListener('click', () => handleActionSelection(action, btn));
    actionButtonsEl.appendChild(btn);
  });

  if (hasDiscards) {
    actionMetaEl.textContent += ' · 點選手牌以打出';
  }

  bindSelfHandInteractions();
}

async function submitAction(actionId, button) {
  if (currentSerial == null) return;
  if (button) {
    if ('disabled' in button) {
      button.disabled = true;
    }
    if (button.classList) {
      button.classList.add('pending');
    }
  }
  try {
    const response = await fetch('/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ serial: currentSerial, action_id: actionId }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail);
    }
  } catch (err) {
    console.error('Failed to submit action', err);
  }
}

function renderSummaries(summaries = []) {
  summaryListEl.innerHTML = '';
  summaries.slice().reverse().forEach((summary) => {
    const card = document.createElement('div');
    card.className = 'summary-card';
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.innerHTML = `牌局 ${summary.hand_index} · 將 ${summary.jang_index ?? '-'} · 莊家 P${summary.dealer_pid ?? '?'}`;
    card.appendChild(meta);
    const winner = document.createElement('div');
    winner.className = 'winner';
    if (summary.winner != null) {
      winner.textContent = `胡牌: P${summary.winner} ${
        summary.win_source ?? ''
      } ${summary.win_tile ?? ''}`;
    } else {
      winner.textContent = '流局';
    }
    card.appendChild(winner);
    if (summary.payments) {
      const pay = document.createElement('div');
      pay.textContent = `得失: ${summary.payments.join(' / ')}`;
      card.appendChild(pay);
    }
    summaryListEl.appendChild(card);
  });
}

function renderReveal(reveal) {
  if (!reveal) {
    revealOverlay.hidden = true;
    revealDismissed = false;
    return;
  }
  if (revealDismissed) {
    return;
  }
  revealContent.innerHTML = '';
  reveal.players.forEach((player) => {
    const block = document.createElement('div');
    block.className = 'reveal-player';
    const header = document.createElement('h3');
    header.textContent = `P${player.pid} ${player.is_dealer ? '(莊)' : ''}`;
    block.appendChild(header);

    const meta = document.createElement('div');
    meta.className = 'reveal-meta';
    if (player.win_source) {
      meta.textContent = `${player.win_source} ${player.win_tile ?? ''}`;
      if (player.ron_from != null) {
        meta.textContent += ` from P${player.ron_from}`;
      }
    }
    block.appendChild(meta);

    const sections = [
      { label: '手牌', tiles: player.hand },
      { label: '副露', melds: player.melds },
      { label: '花牌', tiles: player.flowers },
      { label: '河牌', tiles: player.river },
    ];

    sections.forEach((section) => {
      const container = document.createElement('div');
      container.className = 'player-section';
      const label = document.createElement('div');
      label.className = 'section-label';
      label.textContent = section.label;
      container.appendChild(label);
      const wrap = document.createElement('div');
      wrap.className = 'tiles';
      if (section.tiles) {
        section.tiles.forEach((tile) => wrap.appendChild(makeTile(tile)));
      } else if (section.melds) {
        section.melds.forEach((meld) => {
          const meldWrap = document.createElement('div');
          meldWrap.className = 'tiles';
          meld.tiles.forEach((tile) => meldWrap.appendChild(makeTile(tile)));
          wrap.appendChild(meldWrap);
        });
      }
      container.appendChild(wrap);
      block.appendChild(container);
    });

    revealContent.appendChild(block);
  });

  revealOverlay.hidden = false;
}

closeRevealBtn.addEventListener('click', () => {
  revealDismissed = true;
  revealOverlay.hidden = true;
});

function renderState(state) {
  latestState = state;
  if (!state) return;
  renderPlayers(state.players || []);
  renderStatus(state.status || {});
  renderActions(state.pending_request);
  renderSummaries(state.hand_summaries || []);
  renderReveal(state.reveal);
}

function bindSelfHandInteractions() {
  const slot = document.querySelector('.player-slot.self-player');
  if (!slot) return;
  const tiles = slot.querySelectorAll('.self-hand-strip .tile');
  tiles.forEach((tile) => {
    tile.classList.remove('interactive', 'pending');
    tile.onclick = null;
    const label = tile.dataset.label;
    if (!label || discardActionLookup.size === 0 || currentSerial == null) {
      return;
    }
    const source = tile.dataset.source || 'hand';
    let actionId =
      discardActionLookup.get(`${label}:${source}`) ||
      discardActionLookup.get(`${label}:hand`);
    if (!actionId && source === 'hand') {
      actionId = discardActionLookup.get(`${label}:drawn`);
    }
    if (!actionId) {
      return;
    }
    tile.classList.add('interactive');
    tile.onclick = () => submitAction(actionId, tile);
  });
}

function computeSeatMapping(players) {
  const mapping = { ...defaultSeatToSlot };
  let selfSeat = null;
  players.forEach((player) => {
    if (player.is_self && player.seat) {
      selfSeat = String(player.seat).toUpperCase();
    }
  });
  if (!selfSeat || !windOrder.includes(selfSeat)) {
    return mapping;
  }
  const start = windOrder.indexOf(selfSeat);
  for (let idx = 0; idx < windOrder.length; idx += 1) {
    const seat = windOrder[(start + idx) % windOrder.length];
    mapping[seat] = slotOrder[idx];
  }
  return mapping;
}

function handleActionSelection(action, control, options = {}) {
  if (action.type === 'PASS') {
    actionButtonsEl.innerHTML = '';
    actionMetaEl.textContent = options.auto
      ? '自動 PASS，等待其他玩家…'
      : '已選擇 PASS，等待其他玩家…';
    discardActionLookup.clear();
    bindSelfHandInteractions();
  }
  submitAction(action.id, control);
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    renderState(payload);
  };
  ws.onclose = () => {
    setTimeout(connectWebSocket, 1500);
  };
  ws.onerror = () => {
    ws.close();
  };
}

async function bootstrap() {
  let hasInitialState = false;
  try {
    const response = await fetch('/state');
    if (response.ok) {
      const data = await response.json();
      if (data) {
        renderState(data);
        hasInitialState = true;
      }
    }
  } catch (err) {
    console.warn('Unable to fetch initial state', err);
  }
  if (!hasInitialState) {
    renderState(DEMO_STATE);
  }
  connectWebSocket();
}

bootstrap();
