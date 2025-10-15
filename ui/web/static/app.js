const hudRoundEl = document.getElementById('hud-round');
const hudTurnEl = document.getElementById('hud-turn');
const hudRemainingEl = document.getElementById('hud-remaining');
const hudScoresEl = document.getElementById('hud-scores');
const hudDeltasEl = document.getElementById('hud-deltas');
const centerWindEl = document.getElementById('center-wind');
const centerRoundEl = document.getElementById('center-round');
const centerPhaseEl = document.getElementById('center-phase');
const centerRemainingEl = document.getElementById('center-remaining');
const lastActionEl = document.getElementById('last-action');
const actionMetaEl = document.getElementById('action-meta');
const actionButtonsEl = document.getElementById('action-buttons');
const summaryListEl = document.getElementById('summary-list');
const revealOverlay = document.getElementById('reveal-overlay');
const revealContent = document.getElementById('reveal-content');
const closeRevealBtn = document.getElementById('close-reveal');

const slotEls = {
  north: document.getElementById('slot-north'),
  south: document.getElementById('slot-south'),
  east: document.getElementById('slot-east'),
  west: document.getElementById('slot-west'),
};

const seatToSlot = { E: 'south', S: 'west', W: 'north', N: 'east' };
let currentSerial = null;
let revealDismissed = false;
let latestState = null;
const discardActionLookup = new Map();
let autoPassSerial = null;

const quanLabel = (code) => {
  if (!code) return '?';
  const key = String(code).toUpperCase();
  const mapping = { E: '東', S: '南', W: '西', N: '北' };
  return mapping[key] ?? key;
};

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

function clearSlots() {
  Object.values(slotEls).forEach((slot) => {
    slot.innerHTML = '';
  });
}

function renderStatus(status = {}) {
  const totals = (status.totals || [])
    .map((value, idx) => `P${idx}:${value}`)
    .join(' · ');
  const deltas = (status.deltas || [])
    .map((value, idx) => `P${idx}:${value >= 0 ? '+' : ''}${value}`)
    .join(' · ');
  const last = status.last_action;

  const quan = quanLabel(status.quan_feng);
  const dealer = status.dealer_pid ?? '?';
  const turn = status.turn != null ? `P${status.turn}` : '—';
  const phase = status.phase ?? '—';
  const remaining = status.remaining ?? '—';
  const dead = status.dead_wall ?? '—';

  hudRoundEl.innerHTML = `
    <span class="label">圈風 / 莊家</span>
    <span class="value">${quan} · P${dealer}</span>
  `;
  hudTurnEl.innerHTML = `
    <span class="label">輪到</span>
    <span class="value">${turn}</span>
    <span class="sub">${phase}</span>
  `;
  hudRemainingEl.innerHTML = `
    <span class="label">剩餘牌 / 死牌區</span>
    <span class="value">${remaining}</span>
    <span class="sub">Dead ${dead}</span>
  `;
  hudScoresEl.innerHTML = `
    <span class="label">總分</span>
    <span class="value">${totals || '—'}</span>
  `;
  hudDeltasEl.innerHTML = `
    <span class="label">本局增減</span>
    <span class="value">${deltas || '—'}</span>
  `;

  centerWindEl.textContent = `${quan} ${turn}`;
  centerRoundEl.textContent = remaining;
  centerPhaseEl.textContent = phase;
  centerRemainingEl.textContent = `Dead ${dead} · 莊 P${dealer}`;

  if (last) {
    lastActionEl.innerHTML = `<strong>${last.who ?? ''}</strong> ${
      last.type ?? ''
    } ${last.detail ?? ''}`;
  } else {
    lastActionEl.textContent = '等待更新…';
  }
}

function renderPlayer(slot, player) {
  slot.innerHTML = '';
  slot.dataset.pid = player.pid;
  slot.classList.toggle('self-player', Boolean(player.is_self));

  const card = document.createElement('div');
  card.className = 'player-card';
  slot.appendChild(card);

  const banner = document.createElement('div');
  banner.className = 'player-banner';
  const name = document.createElement('div');
  name.className = 'player-name';
  name.textContent = `P${player.pid}`;
  banner.appendChild(name);

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
  const totals = latestState?.status?.totals;
  if (Array.isArray(totals) && totals[player.pid] != null) {
    addTag(`${totals[player.pid]} 分`);
  }
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

  const meldZone = buildZone('副露', () => {
    if (!player.melds || player.melds.length === 0) {
      return null;
    }
    const wrap = document.createElement('div');
    wrap.className = 'meld-area';
    player.melds.forEach((meld) => {
      const stack = document.createElement('div');
      stack.className = 'meld-stack';
      meld.tiles.forEach((tile) => {
        stack.appendChild(makeTile(tile));
      });
      wrap.appendChild(stack);
    });
    return wrap;
  });
  board.appendChild(meldZone);

  if (!player.is_self) {
    const handZone = buildZone('手牌', () => {
      const wrap = document.createElement('div');
      wrap.className = 'hidden-count';
      wrap.textContent = `${player.hand_count ?? 0} 張`;
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
}

function renderPlayers(players = []) {
  clearSlots();
  const used = new Set();
  const fallback = ['south', 'west', 'north', 'east'];
  players.forEach((player) => {
    const seat = player.seat ? String(player.seat).toUpperCase() : null;
    let slotName = seat && seatToSlot[seat];
    if (!slotName || used.has(slotName)) {
      slotName = fallback.find((name) => !used.has(name)) || 'south';
    }
    used.add(slotName);
    const slot = slotEls[slotName];
    if (slot) {
      renderPlayer(slot, player);
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
  actionMetaEl.textContent = `玩家 P${pending.player} · ${pending.phase} · 牌牆剩餘 ${pending.n_remaining}`;

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
