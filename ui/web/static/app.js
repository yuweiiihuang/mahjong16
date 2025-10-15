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
let currentSerial = null;
let revealDismissed = false;
let latestState = null;
const discardActionLookup = new Map();
let autoPassSerial = null;

const tileSuit = (label) => {
  if (!label) return 'z';
  if (label === '##') return 'concealed';
  const last = label[label.length - 1];
  if ('mps'.includes(last)) return last;
  if ('ESWN'.includes(last)) return 'z';
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
}

function renderPlayer(slot, player, slotName) {
  slot.innerHTML = '';
  slot.dataset.pid = player.pid;
  slot.classList.toggle('self-player', Boolean(player.is_self));

  const card = document.createElement('div');
  card.className = 'player-card';
  slot.appendChild(card);

  const banner = document.createElement('div');
  banner.className = 'player-banner';
  const seatLabel = document.createElement('div');
  seatLabel.className = 'player-seat-label';
  seatLabel.textContent = player.seat ?? '?';
  banner.appendChild(seatLabel);
  card.appendChild(banner);

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
    addTag('YOU', { highlight: true });
    addTag(`${player.hand.length + (player.drawn ? 1 : 0)} 張`, {
      highlight: false,
    });
  } else {
    addTag(`${player.hand_count ?? 0} 張`);
  }
  if (player.is_dealer) addTag('莊', { highlight: true });
  if (player.declared_ting) addTag('聽牌', { highlight: true });
  if (tags.childElementCount > 0) {
    card.appendChild(tags);
  }

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
      renderPlayer(slot, player, slotName);
    }
    const centerSeat = centerSeatEls[slotName];
    if (centerSeat) {
      centerSeat.textContent = `P${player.pid}`;
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
  renderStatus(state.status || {});
  renderPlayers(state.players || []);
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
  try {
    const response = await fetch('/state');
    if (response.ok) {
      const data = await response.json();
      if (data) {
        renderState(data);
      }
    }
  } catch (err) {
    console.warn('Unable to fetch initial state', err);
  }
  connectWebSocket();
}

bootstrap();
